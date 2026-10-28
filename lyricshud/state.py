import json
import time
import math
import threading
import queue

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from lyricshud.effects import shape_colors
from lyricshud.lyrics import fetch_lyrics
from lyricshud.paths import OFFS_PATH
from lyricshud.system import load_total, save_total
from lyricshud.theme import Palette, palette_from_image
from lyricshud.utils import clamp, ease


class State(QObject):
    track_changed = pyqtSignal()
    lyrics_changed = pyqtSignal()
    palette_changed = pyqtSignal()
    lyrics_ready = pyqtSignal(int, object)
    offset_changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.cmds = queue.Queue()
        self.active = False
        self.key = None
        self.title = ""
        self.artist = ""
        self.album = ""
        self.app = ""
        self.playing = False
        self.dur = 0.0
        self.cover = None
        self.cover_id = 0
        self.cover_pal = None
        self.lyrics = None
        self.status = "idle"
        self.can = {}
        self.shuffle = False
        self.repeat = 0
        self.anchor_pos = 0.0
        self.anchor_t = time.monotonic()
        self.hold_play = 0.0
        self.hold_ctrl = 0.0
        self.track_started = time.monotonic()
        self.started = time.monotonic()
        self.songs = 0
        self.songs_total = load_total()
        self.counted = None
        self.fetch_id = 0
        self.rate = 1.0
        self.track_offsets = {}
        self.load_track_offsets()
        self.pal_target = self.compute_palette()
        self.pal_cur = Palette.blend(self.pal_target, self.pal_target, 0.0)
        self.pal_t = time.monotonic()
        self.lyrics_ready.connect(self.on_lyrics_ready)

    @property
    def palette(self):
        return self.pal_cur

    def compute_palette(self):
        if self.cfg["adaptive"] and self.cover_pal is not None:
            a, s = shape_colors(self.cover_pal.accent, self.cover_pal.secondary, self.cfg["adaptive_mode"])
            return Palette(a, s, None, None)
        bg = self.cfg["bg_color"] if self.cfg["custom_bg"] else None
        return Palette(self.cfg["accent"], self.cfg["secondary"], self.cfg["text"], bg)

    def recompute_palette(self):
        self.pal_target = self.compute_palette()
        self.palette_changed.emit()

    def step_palette(self):
        now = time.monotonic()
        dt = min(0.1, now - self.pal_t)
        self.pal_t = now
        if self.pal_cur.close_to(self.pal_target):
            if self.pal_cur is not self.pal_target:
                self.pal_cur = Palette.blend(self.pal_target, self.pal_target, 0.0)
            return False
        self.pal_cur = Palette.blend(self.pal_cur, self.pal_target, 1.0 - math.exp(-dt * 5.0))
        return True

    def position(self):
        p = self.anchor_pos
        if self.playing:
            p += (time.monotonic() - self.anchor_t) * self.rate
        if self.dur > 0:
            p = min(p, self.dur)
        return max(0.0, p)

    def lyric_time(self):
        return self.position() + (self.cfg["offset_ms"] + self.track_ms() + self.cfg["anticipation"]) / 1000.0

    def active_lines(self):
        ly = self.lyrics
        if ly is None:
            return []
        t = self.lyric_time()
        hold = self.cfg["hold"] / 100.0
        fo = self.cfg["fade_ms"] / 1000.0
        fi = fo * 0.65
        idx = ly.index_at(t)
        out = []
        for i in range(max(0, idx - 2), idx + 1):
            if i >= len(ly.texts) or not ly.texts[i]:
                continue
            s, e = ly.span(i, hold)
            if t < s:
                continue
            eo = clamp((t - e) / fo, 0.0, 1.0)
            if eo >= 1.0:
                continue
            a = ease((t - s) / fi) * (1.0 - ease(eo))
            prog = clamp((t - s) / ly.sing(i), 0.0, 1.0)
            life = clamp((t - s) / max(0.2, (e - s) + fo), 0.0, 1.0)
            out.append((i, a, prog, t - s, eo, life))
        return out

    def set_cover(self, data):
        img = QImage.fromData(data)
        if img.isNull():
            return False
        self.cover = img
        self.cover_id += 1
        self.cover_pal = palette_from_image(img)
        self.recompute_palette()
        return True

    def on_media(self, d):
        if not d.get("active"):
            if self.active:
                self.active = False
                self.playing = False
                self.key = None
                self.counted = None
                self.lyrics = None
                self.status = "idle"
                self.cover = None
                self.cover_pal = None
                self.fetch_id += 1
                self.recompute_palette()
                self.track_changed.emit()
            return
        self.rate = float(d.get("rate", 1.0) or 1.0)
        self.app = d.get("app", "") or ""
        changed = d["key"] != self.key
        notify = changed
        now = time.monotonic()
        if changed:
            self.key = d["key"]
            self.title = d["title"]
            self.artist = d["artist"]
            self.album = d["album"]
            self.dur = d["dur"]
            self.cover = None
            self.lyrics = None
            self.status = "loading"
            self.anchor_pos = d["pos"]
            self.anchor_t = now
            self.playing = d["playing"]
            self.active = True
            self.track_started = now
            self.request_lyrics()
        else:
            if d["dur"] > 0:
                self.dur = d["dur"]
            est = self.position()
            if now >= self.hold_play:
                if d["playing"] != self.playing or abs(d["pos"] - est) > 0.6:
                    self.anchor_pos = d["pos"]
                    self.anchor_t = now
                else:
                    self.anchor_pos += (d["pos"] - est) * 0.25
                self.playing = d["playing"]
        self.can = d.get("can", {})
        if now >= self.hold_ctrl:
            self.shuffle = d.get("shuffle", False)
            self.repeat = d.get("repeat", 0)
        if self.playing and self.key != self.counted:
            self.counted = self.key
            self.songs += 1
            self.songs_total += 1
            save_total(self.songs_total)
        if d.get("cover") and self.set_cover(d["cover"]):
            notify = True
        if notify:
            self.track_changed.emit()

    def request_lyrics(self):
        self.fetch_id += 1
        threading.Thread(
            target=self.fetch_worker,
            args=(self.fetch_id, self.title, self.artist, self.album, self.dur),
            daemon=True,
        ).start()

    def fetch_worker(self, fid, title, artist, album, dur):
        try:
            res = fetch_lyrics(title, artist, album, dur)
        except Exception:
            res = None
        self.lyrics_ready.emit(fid, res)

    def on_lyrics_ready(self, fid, res):
        if fid != self.fetch_id:
            return
        self.lyrics = res
        self.status = "found" if res else "none"
        self.lyrics_changed.emit()

    def toggle_play(self):
        now = time.monotonic()
        self.anchor_pos = self.position()
        self.anchor_t = now
        self.playing = not self.playing
        self.hold_play = now + 0.8
        self.cmds.put(("toggle", None))

    def skip_next(self):
        self.cmds.put(("next", None))

    def skip_prev(self):
        self.cmds.put(("prev", None))

    def seek(self, sec):
        now = time.monotonic()
        self.anchor_pos = clamp(sec, 0.0, self.dur if self.dur > 0 else sec)
        self.anchor_t = now
        self.hold_play = now + 0.8
        self.cmds.put(("seek", self.anchor_pos))

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.hold_ctrl = time.monotonic() + 1.2
        self.cmds.put(("shuffle", self.shuffle))

    def cycle_repeat(self):
        self.repeat = {0: 2, 2: 1, 1: 0}.get(self.repeat, 0)
        self.hold_ctrl = time.monotonic() + 1.2
        self.cmds.put(("repeat", self.repeat))

    def track_key(self):
        if not self.active:
            return None
        return f"{self.artist}|{self.title}|{int(round(self.dur))}".lower()

    def track_ms(self):
        if not self.cfg["auto_sync"]:
            return 0
        k = self.track_key()
        return int(self.track_offsets.get(k, 0)) if k else 0

    def sync_ms(self):
        if self.cfg["auto_sync"] and self.active:
            return self.track_ms()
        return int(self.cfg["offset_ms"])

    def snap(self, which):
        ly = self.lyrics
        if ly is None or not self.active:
            return False
        pos = self.position()
        idx = ly.index_at(self.lyric_time() - self.cfg["anticipation"] / 1000.0)
        target = idx + which
        if target < 0:
            return False
        while target < len(ly.texts) and not ly.texts[target]:
            target += 1
        if target >= len(ly.texts):
            return False
        total = int(round((ly.times[target] - pos) * 1000.0))
        if self.cfg["auto_sync"]:
            self.set_track_ms(total - int(self.cfg["offset_ms"]))
        else:
            self.cfg["offset_ms"] = int(clamp(total, -5000, 5000))
            self.offset_changed.emit()
        return True

    def load_track_offsets(self):
        try:
            data = json.loads(OFFS_PATH.read_text("utf-8"))
            if isinstance(data, dict):
                self.track_offsets = {str(k): int(v) for k, v in data.items()}
        except Exception:
            self.track_offsets = {}

    def set_track_ms(self, v):
        k = self.track_key()
        if not k:
            return
        v = int(clamp(v, -5000, 5000))
        if v:
            self.track_offsets[k] = v
        else:
            self.track_offsets.pop(k, None)
        try:
            OFFS_PATH.write_text(json.dumps(self.track_offsets, indent=2, ensure_ascii=False), "utf-8")
        except Exception:
            pass
        self.offset_changed.emit()
