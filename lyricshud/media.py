import time
import asyncio
import queue
from datetime import datetime
from pathlib import Path
from urllib import request as urlrequest
from urllib import parse as urlparse

from PyQt6.QtCore import QThread, pyqtSignal

from lyricshud.boot import IS_WIN
from lyricshud.utils import clamp


open_dbus_connection = None
if IS_WIN:
    from winrt.windows.media import MediaPlaybackAutoRepeatMode
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )
    from winrt.windows.storage.streams import Buffer, InputStreamOptions, DataReader
else:
    try:
        from jeepney import DBusAddress, Properties, new_method_call
        from jeepney.bus_messages import message_bus
        from jeepney.io.blocking import open_dbus_connection
    except Exception:
        open_dbus_connection = None


async def read_thumb(ref):
    try:
        stream = await ref.open_read_async()
        size = int(stream.size)
        if size <= 0:
            return None
        buf = Buffer(size)
        await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
        try:
            data = bytes(memoryview(buf))
        except Exception:
            reader = DataReader.from_buffer(buf)
            arr = bytearray(buf.length)
            reader.read_bytes(arr)
            data = bytes(arr)
        try:
            stream.close()
        except Exception:
            pass
        return data if data else None
    except Exception:
        return None


class MediaWorker(QThread):
    media = pyqtSignal(dict)

    def __init__(self, cmds):
        super().__init__()
        self._run = True
        self.cmds = cmds
        self.session = None
        self.next_poll = 0.0
        self.last_key = None
        self.cover_sent = False
        self.tries = 0
        self.fb_pos = 0.0
        self.fb_t = time.monotonic()

    def stop(self):
        self._run = False

    def run(self):
        try:
            asyncio.run(self.loop())
        except Exception as e:
            print("Media worker stopped:", e)

    @staticmethod
    def pick(mgr):
        cur = mgr.get_current_session()
        try:
            if cur is not None and cur.get_playback_info().playback_status == PlaybackStatus.PLAYING:
                return cur
            for s in mgr.get_sessions():
                if s.get_playback_info().playback_status == PlaybackStatus.PLAYING:
                    return s
        except Exception:
            pass
        return cur

    @staticmethod
    def read_timeline(tl, playing, rate=1.0):
        start = tl.start_time.total_seconds()
        end = tl.end_time.total_seconds()
        pos = tl.position.total_seconds() - start
        dur = max(0.0, end - start)
        if playing:
            lu = tl.last_updated_time
            if lu is not None:
                try:
                    now = datetime.now(lu.tzinfo) if lu.tzinfo else datetime.now()
                    delta = (now - lu).total_seconds()
                    if delta > 0:
                        pos += delta * rate
                except Exception:
                    pass
        if dur > 0:
            pos = min(pos, dur)
        return max(0.0, pos), dur

    async def drain(self):
        while True:
            try:
                cmd, arg = self.cmds.get_nowait()
            except queue.Empty:
                return
            s = self.session
            if s is None:
                continue
            try:
                if cmd == "toggle":
                    await s.try_toggle_play_pause_async()
                elif cmd == "next":
                    await s.try_skip_next_async()
                elif cmd == "prev":
                    await s.try_skip_previous_async()
                elif cmd == "seek":
                    await s.try_change_playback_position_async(int(arg * 10000000))
                elif cmd == "shuffle":
                    await s.try_change_shuffle_active_async(bool(arg))
                elif cmd == "repeat":
                    await s.try_change_auto_repeat_mode_async(MediaPlaybackAutoRepeatMode(int(arg)))
            except Exception:
                pass
            self.next_poll = min(self.next_poll, time.monotonic() + 0.15)

    async def poll(self, mgr):
        session = self.pick(mgr)
        self.session = session
        active = False
        info = None
        status = None
        if session is not None:
            info = await session.try_get_media_properties_async()
            title = info.title or ""
            artist = info.artist or ""
            album = info.album_title or ""
            pb = session.get_playback_info()
            status = pb.playback_status
            if title and status not in (PlaybackStatus.STOPPED, PlaybackStatus.CLOSED):
                active = True
        if not active:
            self.last_key = None
            self.media.emit({"active": False})
            return
        playing = status == PlaybackStatus.PLAYING
        rate = 1.0
        try:
            rr = pb.playback_rate
            if rr:
                rate = clamp(float(rr), 0.25, 4.0)
        except Exception:
            pass
        pos, dur = self.read_timeline(session.get_timeline_properties(), playing, rate)
        key = f"{title}|{artist}|{album}"
        now = time.monotonic()
        if key != self.last_key:
            self.last_key = key
            self.cover_sent = False
            self.tries = 0
            self.fb_pos = 0.0
        if playing:
            self.fb_pos += now - self.fb_t
        self.fb_t = now
        if dur <= 0 and pos <= 0:
            pos = self.fb_pos
        can = {}
        try:
            c = pb.controls
            can = {
                "prev": bool(c.is_previous_enabled),
                "next": bool(c.is_next_enabled),
                "play": bool(c.is_play_enabled or c.is_pause_enabled or c.is_play_pause_toggle_enabled),
                "seek": bool(c.is_playback_position_enabled),
                "shuffle": bool(c.is_shuffle_enabled),
                "repeat": bool(c.is_repeat_enabled),
            }
        except Exception:
            can = {}
        shuffle = False
        repeat = 0
        try:
            sh = pb.is_shuffle_active
            shuffle = bool(sh) if sh is not None else False
            rm = pb.auto_repeat_mode
            repeat = int(rm) if rm is not None else 0
        except Exception:
            pass
        app_id = ""
        try:
            app_id = str(session.source_app_user_model_id or "")
        except Exception:
            app_id = ""
        payload = {
            "active": True,
            "key": key,
            "title": title,
            "artist": artist,
            "album": album,
            "playing": playing,
            "pos": pos,
            "dur": dur,
            "cover": None,
            "can": can,
            "shuffle": shuffle,
            "repeat": repeat,
            "rate": rate,
            "app": app_id,
        }
        if not self.cover_sent and self.tries < 8:
            self.tries += 1
            if info.thumbnail is not None:
                data = await read_thumb(info.thumbnail)
                if data:
                    self.cover_sent = True
                    payload["cover"] = data
        self.media.emit(payload)

    async def loop(self):
        mgr = await SessionManager.request_async()
        while self._run:
            try:
                await self.drain()
                now = time.monotonic()
                if now >= self.next_poll:
                    self.next_poll = now + 0.25
                    await self.poll(mgr)
            except Exception:
                pass
            await asyncio.sleep(0.07)


class MprisWorker(QThread):
    media = pyqtSignal(dict)
    PATH = "/org/mpris/MediaPlayer2"
    IFACE = "org.mpris.MediaPlayer2.Player"

    def __init__(self, cmds):
        super().__init__()
        self._run = True
        self.cmds = cmds
        self.conn = None
        self.name = None
        self.trackid = "/org/mpris/MediaPlayer2/TrackList/NoTrack"
        self.next_poll = 0.0
        self.last_key = None
        self.cover_sent = False
        self.tries = 0
        self.fb_pos = 0.0
        self.fb_t = time.monotonic()

    def stop(self):
        self._run = False

    def addr(self, name):
        return DBusAddress(self.PATH, bus_name=name, interface=self.IFACE)

    def call(self, msg):
        return self.conn.send_and_get_reply(msg, timeout=2.0)

    def close_conn(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None

    def players(self):
        r = self.call(message_bus.ListNames())
        return [n for n in r.body[0] if str(n).startswith("org.mpris.MediaPlayer2.")]

    def props(self, name):
        try:
            r = self.call(Properties(self.addr(name)).get_all())
            return {k: v[1] for k, v in r.body[0].items()}
        except Exception:
            return None

    @staticmethod
    def num(v, d=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    @staticmethod
    def load_art(url):
        if not url:
            return None
        try:
            url = str(url)
            if url.startswith("file://"):
                return Path(urlparse.unquote(urlparse.urlparse(url).path)).read_bytes()
            req = urlrequest.Request(url, headers={"User-Agent": "LyricsHUD"})
            with urlrequest.urlopen(req, timeout=6) as r:
                return r.read(8000000)
        except Exception:
            return None

    def drain(self):
        while True:
            try:
                cmd, arg = self.cmds.get_nowait()
            except queue.Empty:
                return
            if self.name is None:
                continue
            addr = self.addr(self.name)
            try:
                if cmd == "toggle":
                    msg = new_method_call(addr, "PlayPause")
                elif cmd == "next":
                    msg = new_method_call(addr, "Next")
                elif cmd == "prev":
                    msg = new_method_call(addr, "Previous")
                elif cmd == "seek":
                    msg = new_method_call(addr, "SetPosition", "ox", (self.trackid, int(float(arg) * 1000000)))
                elif cmd == "shuffle":
                    msg = Properties(addr).set("Shuffle", "b", bool(arg))
                elif cmd == "repeat":
                    msg = Properties(addr).set("LoopStatus", "s", {0: "None", 1: "Track", 2: "Playlist"}.get(int(arg), "None"))
                else:
                    continue
                self.call(msg)
            except Exception:
                pass
            self.next_poll = min(self.next_poll, time.monotonic() + 0.15)

    def poll(self):
        best = None
        pr = None
        for n in self.players():
            cur = self.props(n)
            if not cur:
                continue
            if cur.get("PlaybackStatus") == "Playing":
                best, pr = n, cur
                break
            if best is None or n == self.name:
                best, pr = n, cur
        self.name = best
        if pr is None:
            self.last_key = None
            self.media.emit({"active": False})
            return
        raw = pr.get("Metadata")
        meta = {k: v[1] for k, v in raw.items()} if isinstance(raw, dict) else {}
        title = str(meta.get("xesam:title") or "")
        art = meta.get("xesam:artist") or []
        artist = ", ".join(str(a) for a in art) if isinstance(art, (list, tuple)) else str(art)
        album = str(meta.get("xesam:album") or "")
        status = pr.get("PlaybackStatus")
        if not title or status == "Stopped":
            self.last_key = None
            self.media.emit({"active": False})
            return
        self.trackid = str(meta.get("mpris:trackid") or self.trackid)
        playing = status == "Playing"
        dur = max(0.0, self.num(meta.get("mpris:length")) / 1000000.0)
        pos = max(0.0, self.num(pr.get("Position")) / 1000000.0)
        if dur > 0:
            pos = min(pos, dur)
        rate = clamp(self.num(pr.get("Rate"), 1.0) or 1.0, 0.25, 4.0)
        key = f"{title}|{artist}|{album}"
        now = time.monotonic()
        if key != self.last_key:
            self.last_key = key
            self.cover_sent = False
            self.tries = 0
            self.fb_pos = 0.0
        if playing:
            self.fb_pos += now - self.fb_t
        self.fb_t = now
        if dur <= 0 and pos <= 0:
            pos = self.fb_pos
        payload = {
            "active": True,
            "key": key,
            "title": title,
            "artist": artist,
            "album": album,
            "playing": playing,
            "pos": pos,
            "dur": dur,
            "cover": None,
            "can": {
                "prev": bool(pr.get("CanGoPrevious", True)),
                "next": bool(pr.get("CanGoNext", True)),
                "play": bool(pr.get("CanPlay", True) or pr.get("CanPause", True)),
                "seek": bool(pr.get("CanSeek", False)),
                "shuffle": "Shuffle" in pr,
                "repeat": "LoopStatus" in pr,
            },
            "shuffle": bool(pr.get("Shuffle", False)),
            "repeat": {"None": 0, "Track": 1, "Playlist": 2}.get(str(pr.get("LoopStatus", "None")), 0),
            "rate": rate,
            "app": str(self.name or "").replace("org.mpris.MediaPlayer2.", ""),
        }
        if not self.cover_sent and self.tries < 8:
            self.tries += 1
            data = self.load_art(meta.get("mpris:artUrl"))
            if data:
                self.cover_sent = True
                payload["cover"] = data
        self.media.emit(payload)

    def run(self):
        while self._run:
            try:
                if self.conn is None:
                    if open_dbus_connection is None:
                        raise RuntimeError("jeepney is not installed")
                    self.conn = open_dbus_connection(bus="SESSION")
                self.drain()
                now = time.monotonic()
                if now >= self.next_poll:
                    self.next_poll = now + 0.25
                    self.poll()
            except Exception:
                self.close_conn()
                self.name = None
                self.media.emit({"active": False})
                for _ in range(25):
                    if not self._run:
                        break
                    time.sleep(0.1)
                continue
            time.sleep(0.07)
        self.close_conn()
