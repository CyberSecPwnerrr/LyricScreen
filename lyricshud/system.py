import sys
import os
import json
import subprocess
from pathlib import Path

from lyricshud.boot import APP_NAME, FROZEN, IS_WIN, _install_dir, _same_path
from lyricshud.paths import STATS_PATH


def load_total():
    try:
        return max(0, int(json.loads(STATS_PATH.read_text("utf-8")).get("songs", 0)))
    except Exception:
        return 0


def save_total(n):
    try:
        STATS_PATH.write_text(json.dumps({"songs": int(n)}), "utf-8")
    except Exception:
        pass


def fmt_uptime(sec):
    s = int(max(0, sec))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def startup_args():
    if FROZEN:
        args = [os.environ.get("APPIMAGE") or sys.executable]
        if IS_WIN and not _same_path(Path(sys.executable).parent, _install_dir()):
            args.append("--no-install")
        return args
    exe = sys.executable
    if IS_WIN:
        w = Path(exe).with_name("pythonw.exe")
        if w.exists():
            exe = str(w)
    return [exe, os.path.abspath(sys.modules["__main__"].__file__)]


def set_startup(on):
    try:
        args = startup_args()
        if IS_WIN:
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                if on:
                    winreg.SetValueEx(k, "LyricsScreen", 0, winreg.REG_SZ, subprocess.list2cmdline(args))
                else:
                    try:
                        winreg.DeleteValue(k, "LyricsScreen")
                    except FileNotFoundError:
                        pass
            return True
        d = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart"
        f = d / "LyricsScreen.desktop"
        if on:
            d.mkdir(parents=True, exist_ok=True)
            line = " ".join(
                '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'
                for a in args
            )
            f.write_text(
                "[Desktop Entry]\nType=Application\nName=" + APP_NAME + "\nExec=" + line + "\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
                "utf-8",
            )
        elif f.exists():
            f.unlink()
        return True
    except Exception:
        return False
