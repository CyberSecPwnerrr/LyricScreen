import os

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QSystemTrayIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from lyricshud.boot import APP_NAME, IS_WIN
from lyricshud.clock import Clock
from lyricshud.config import Config
from lyricshud.floating import Equalizer, Stats
from lyricshud.holo import Holo
from lyricshud.hotkeys import HOTKEY_ACTIONS, HotkeyWorker, parse_hotkey
from lyricshud.hud import Hud
from lyricshud.images import set_text_image
from lyricshud.media import MediaWorker, MprisWorker
from lyricshud.monitor import Monitor
from lyricshud.orbital import OrbitalMenu, QuickPanel, make_icon
from lyricshud.settings import SettingsDialog
from lyricshud.state import State
from lyricshud.system import set_startup
from lyricshud.theme import Theme, apply_qss
from lyricshud.themes import CARD_SIZES
from lyricshud.updater import Updater
from lyricshud.utils import clamp, fullscreen_app_active
from lyricshud.volume import VolumeControl
from lyricshud.welcome import Welcome
from lyricshud.widgets import GlassMenu


class Controller:
    MODES = ("hud", "holo", "both")

    def __init__(self, app):
        self.app = app
        self.cfg = Config()
        set_text_image(self.cfg, self.on_text_frame)
        self.theme = Theme(self.cfg)
        self.state = State(self.cfg)
        self.volume = VolumeControl()
        self.vol_level = 0.5
        self.vol_muted = False
        self.hud = Hud(self)
        self.holo = Holo(self)
        self.clock = Clock(self)
        self.monitor = Monitor(self)
        self.stats = Stats(self)
        self.equalizer = Equalizer(self)
        self.updater = Updater(self)
        self.update_notify = False
        self.updater.final.connect(self.on_update_final)
        self.welcome = Welcome(self)
        self.orbital = OrbitalMenu(self)
        self.settings = None
        self.quick = None
        self.player = None
        self.audio_out = None
        self.menu = self.build_menu()
        self.tray = QSystemTrayIcon(make_icon(self.state.pal_target))
        self.tray.setToolTip("Lyrics HUD")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        self.state.palette_changed.connect(self.on_palette)
        self.on_palette()
        self.worker = MediaWorker(self.state.cmds) if IS_WIN else MprisWorker(self.state.cmds)
        self.worker.media.connect(self.state.on_media)
        self.worker.start()
        self.hotkeys = None
        self.vol_timer = QTimer()
        self.vol_timer.timeout.connect(self.poll_volume)
        self.vol_timer.start(500)
        self.poll_volume()
        self.fs_hidden = False
        self.fs_timer = QTimer()
        self.fs_timer.timeout.connect(self.poll_fullscreen)
        self.fs_timer.start(1000)
        self.apply_mode()
        self.apply_hotkeys()
        first = not self.cfg["welcomed"]
        self.cfg["welcomed"] = True
        self.cfg.save()
        self.play_launch()
        if self.cfg["show_welcome"]:
            self.welcome.play(first)
        if self.cfg["startup"]:
            set_startup(True)
        if self.cfg["auto_update"]:
            QTimer.singleShot(6000, self.updater.check)
        app.aboutToQuit.connect(self.shutdown)

    def build_menu(self):
        m = GlassMenu(self)
        m.addAction("Play / pause", self.state.toggle_play)
        m.addAction("Next track", self.state.skip_next)
        m.addAction("Previous track", self.state.skip_prev)
        m.addSeparator()
        m.addAction("Show / hide", self.toggle_visible)
        m.addAction("Orbital menu", self.open_orbital)
        sub = GlassMenu(self, m)
        sub.setTitle("Display mode")
        m.addMenu(sub)
        group = QActionGroup(sub)
        group.setExclusive(True)
        self.mode_actions = {}
        for label, val in (("Player card", "hud"), ("Floating lyrics", "holo"), ("Card + floating lyrics", "both")):
            a = QAction(label, sub)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, v=val: self.set_mode(v))
            group.addAction(a)
            sub.addAction(a)
            self.mode_actions[val] = a
        self.act_lock = QAction("Lock card in place", m)
        self.act_lock.setCheckable(True)
        self.act_lock.triggered.connect(self.toggle_lock)
        m.addAction(self.act_lock)
        self.act_adaptive = QAction("Match album art colors", m)
        self.act_adaptive.setCheckable(True)
        self.act_adaptive.triggered.connect(self.toggle_adaptive)
        m.addAction(self.act_adaptive)
        m.addSeparator()
        m.addAction("Lyrics earlier (+100 ms)", lambda: self.nudge(100))
        m.addAction("Lyrics later (-100 ms)", lambda: self.nudge(-100))
        m.addAction("Reset sync offset", lambda: self.nudge(None))
        m.addAction("Sync: current line starts now", lambda: self.snap(0))
        m.addAction("Sync: next line starts now", lambda: self.snap(1))
        m.addSeparator()
        m.addAction("Settings", lambda: self.open_settings())
        m.addAction("Quick customize", self.open_quick)
        m.addAction("Check for updates", self.check_updates)
        m.addAction("Reset card position", self.reset_hud)
        m.addSeparator()
        m.addAction("Quit", self.app.quit)
        m.aboutToShow.connect(self.sync_menu)
        return m

    def on_palette(self):
        pal = self.state.pal_target
        apply_qss(self.menu, pal, self.theme.family)
        self.tray.setIcon(make_icon(pal))
        self.hud.dirty = True
        self.holo.dirty = True
        self.clock.dirty = True

    def sync_menu(self):
        self.act_lock.setChecked(bool(self.cfg["click_through"]))
        self.act_adaptive.setChecked(bool(self.cfg["adaptive"]))
        for val, a in self.mode_actions.items():
            a.setChecked(self.cfg["mode"] == val)

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        self.cfg["visible"] = not self.cfg["visible"]
        self.apply_mode()
        self.cfg.save()

    def poll_fullscreen(self):
        if not self.cfg["autohide_fullscreen"]:
            if self.fs_hidden:
                self.fs_hidden = False
                self.apply_mode()
            return
        full = fullscreen_app_active()
        if full and not self.fs_hidden:
            self.fs_hidden = True
            for w in (self.hud, self.holo, self.clock, self.monitor, self.stats, self.equalizer):
                w.hide()
        elif not full and self.fs_hidden:
            self.fs_hidden = False
            self.apply_mode()

    def hide_all(self):
        self.cfg["visible"] = False
        self.apply_mode()
        self.cfg.save()

    def toggle_lock(self):
        self.cfg["click_through"] = not self.cfg["click_through"]
        self.refresh()

    def toggle_adaptive(self):
        self.cfg["adaptive"] = not self.cfg["adaptive"]
        self.refresh()
        if self.settings is not None and self.settings.isVisible():
            self.settings.reopen()

    def play_launch(self, force=False):
        path = self.cfg["launch_audio"]
        if not (force or self.cfg["launch_audio_on"]) or not path or not os.path.isfile(path):
            return
        if self.player is None:
            self.audio_out = QAudioOutput()
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.audio_out)
        self.audio_out.setVolume(self.cfg["launch_audio_volume"] / 100.0)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def set_mode(self, mode):
        self.cfg["mode"] = mode
        self.cfg["visible"] = True
        self.refresh()

    def cycle_mode(self):
        i = self.MODES.index(self.cfg["mode"]) if self.cfg["mode"] in self.MODES else 0
        self.set_mode(self.MODES[(i + 1) % len(self.MODES)])

    def nudge(self, delta):
        st = self.state
        if self.cfg["auto_sync"] and st.active:
            if delta is None:
                st.set_track_ms(0)
                self.cfg["offset_ms"] = 0
            else:
                st.set_track_ms(st.track_ms() + delta)
        elif delta is None:
            self.cfg["offset_ms"] = 0
        else:
            self.cfg["offset_ms"] = int(clamp(self.cfg["offset_ms"] + delta, -5000, 5000))
        self.cfg.save()
        self.hud.dirty = True

    def reset_hud(self):
        self.hud.reset_pos()

    def reset_clock(self):
        self.clock.reset_pos()

    def on_text_frame(self):
        if self.state.active and self.state.lyrics is not None:
            self.hud.dirty = True
            self.holo.dirty = True

    def bump(self, key, delta, lo, hi):
        self.cfg[key] = int(clamp(self.cfg[key] + delta, lo, hi))
        self.refresh()

    def set_card_size(self, key):
        w, h = CARD_SIZES.get(key, CARD_SIZES["medium"])
        s = self.hud.scale
        self.cfg["card_size"] = key
        self.cfg["hud_w"] = int(w * s)
        self.cfg["hud_h"] = int(h * s)
        self.refresh()
        self.hud.resize(int(w * s), int(h * s))
        self.hud.save_geometry()

    def poll_volume(self):
        self.volume.app = self.state.app
        self.volume.per_app = bool(self.cfg["app_volume"])
        r = self.volume.get()
        if r is None:
            return
        if r != (self.vol_level, self.vol_muted):
            self.vol_level, self.vol_muted = r
            self.hud.dirty = True

    def set_volume(self, v):
        v = clamp(v, 0.0, 1.0)
        self.volume.set(v)
        self.vol_level = v
        self.vol_muted = False
        self.hud.dirty = True

    def change_volume(self, d):
        self.set_volume(self.vol_level + d)

    def toggle_mute(self):
        self.vol_muted = not self.vol_muted
        self.volume.set_mute(self.vol_muted)
        self.hud.dirty = True

    def open_settings(self, page=0):
        if self.settings is not None and self.settings.isVisible():
            if self.settings.isMinimized():
                self.settings.showNormal()
            self.settings.raise_()
            self.settings.activateWindow()
            return
        self.settings = SettingsDialog(self, page)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def open_orbital(self):
        self.orbital.pop()

    def check_updates(self):
        self.update_notify = True
        self.updater.check()

    def on_update_final(self, text):
        if self.update_notify:
            self.update_notify = False
            self.tray.showMessage(APP_NAME, text)

    def apply_startup(self):
        set_startup(bool(self.cfg["startup"]))

    def open_quick(self):
        if self.quick is not None and self.quick.isVisible():
            self.quick.raise_()
            self.quick.activateWindow()
            return
        self.quick = QuickPanel(self)
        self.quick.show()

    def apply_mode(self):
        mode = self.cfg["mode"]
        visible = bool(self.cfg["visible"])
        if visible and mode in ("hud", "both"):
            if not self.hud.isVisible():
                self.hud.show()
        else:
            self.hud.hide()
        if visible and self.cfg["show_clock"]:
            if not self.clock.isVisible():
                self.clock.show()
        else:
            self.clock.hide()
        if visible and self.cfg["monitor_on"]:
            if not self.monitor.isVisible():
                self.monitor.show()
        else:
            self.monitor.hide()
        if visible and self.cfg["stats_on"]:
            if not self.stats.isVisible():
                self.stats.show()
        else:
            self.stats.hide()
        if visible and self.cfg["eq_on"]:
            if not self.equalizer.isVisible():
                self.equalizer.show()
        else:
            self.equalizer.hide()
        if visible and mode in ("holo", "both"):
            self.holo.place()
            self.holo.attach_wall()
            if not self.holo.isVisible():
                self.holo.show()
        else:
            self.holo.hide()

    def refresh(self):
        set_text_image(self.cfg, self.on_text_frame)
        self.theme.reload()
        self.state.recompute_palette()
        self.hud.refresh()
        self.holo.refresh()
        self.clock.refresh()
        self.monitor.refresh()
        self.stats.refresh()
        self.equalizer.refresh()
        self.apply_mode()
        self.apply_hotkeys()
        if self.audio_out is not None:
            self.audio_out.setVolume(self.cfg["launch_audio_volume"] / 100.0)
        if self.settings is not None and self.settings.isVisible():
            self.settings.preview.refresh()
            self.settings.update()
        self.cfg.save()

    def shutdown(self):
        self.stop_hotkeys()
        if self.player is not None:
            self.player.stop()
        self.worker.stop()
        self.worker.wait(1500)
        self.hud.save_geometry()
        self.cfg.save()
        self.tray.hide()

    def snap(self, which):
        if self.state.snap(which):
            self.cfg.save()
            self.hud.dirty = True

    def hotkey_items(self):
        out = []
        for name, _, key in HOTKEY_ACTIONS:
            parsed = parse_hotkey(self.cfg[key])
            if parsed is not None:
                out.append((name, parsed[0], parsed[1]))
        return out

    def restart_hotkeys(self):
        self.stop_hotkeys()
        self.apply_hotkeys()

    def apply_hotkeys(self):
        if IS_WIN and self.cfg["hotkeys"] and self.hotkeys is None:
            self.hotkeys = HotkeyWorker(self.hotkey_items())
            self.hotkeys.fired.connect(self.on_hotkey)
            self.hotkeys.start()
        elif not self.cfg["hotkeys"]:
            self.stop_hotkeys()

    def stop_hotkeys(self):
        if self.hotkeys is not None:
            self.hotkeys.stop()
            self.hotkeys.wait(1500)
            self.hotkeys = None

    def on_hotkey(self, name):
        if name == "later":
            self.nudge(-100)
        elif name == "earlier":
            self.nudge(100)
        elif name == "reset":
            self.nudge(None)
        elif name == "snap":
            self.snap(1)
        elif name == "toggle":
            self.toggle_visible()
        elif name == "orbital":
            self.open_orbital()
