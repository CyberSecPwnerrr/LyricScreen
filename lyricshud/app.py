import sys
import os
import asyncio
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from lyricshud.boot import IS_WIN
from lyricshud.controller import Controller
from lyricshud.media import open_dbus_connection
from lyricshud.volume import VolumeControl

if IS_WIN:
    from lyricshud.media import SessionManager


def selftest():
    lines = []
    code = 0
    try:
        app = QApplication(sys.argv[:1])
        lines.append("PyQt6 OK")
    except Exception as e:
        lines.append("PyQt6 FAILED: %r" % (e,))
        code = 2
    if IS_WIN:
        try:
            async def go():
                mgr = await SessionManager.request_async()
                mgr.get_sessions()

            asyncio.run(go())
            lines.append("winrt media session OK")
        except Exception as e:
            lines.append("winrt media session FAILED: %r" % (e,))
            code = 2
    else:
        try:
            conn = open_dbus_connection(bus="SESSION")
            conn.close()
            lines.append("D-Bus session OK")
        except Exception as e:
            lines.append("D-Bus session FAILED: %r" % (e,))
            code = 2
    try:
        lines.append("volume control: " + ("OK" if VolumeControl().available else "unavailable (optional)"))
    except Exception as e:
        lines.append("volume control: unavailable (%r)" % (e,))
    try:
        out = Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or Path.home()) / "LyricsScreen_selftest.txt"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass
    return code


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("LyricsHUD")
    app.setQuitOnLastWindowClosed(False)
    ctl = Controller(app)
    code = app.exec()
    del ctl
    sys.exit(code)
