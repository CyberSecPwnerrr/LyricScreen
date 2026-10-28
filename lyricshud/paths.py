import sys
import os
import subprocess
from pathlib import Path

from lyricshud.boot import FROZEN, IS_WIN, _install_dir, _is_admin, _run_elevated, _same_path


if IS_WIN:
    APP_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "LyricsHUD"
else:
    APP_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "LyricsHUD"
CACHE_DIR = APP_DIR / "cache"
CFG_PATH = APP_DIR / "config.json"
OFFS_PATH = APP_DIR / "track_offsets.json"
STATS_PATH = APP_DIR / "stats.json"
PROFILE_DIR = APP_DIR / "profiles"
ASSET_DIR = APP_DIR / "assets"
UPDATE_DIR = APP_DIR / "updates"
APP_VERSION = "1.1.0"
REPO_DEFAULT = "CyberSecPwnerrr/LyricScreen"
APP_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)
UPDATE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_font_dir():
    base = Path(sys.executable).parent if FROZEN else Path(os.path.abspath(sys.modules["__main__"].__file__)).parent
    if (
        IS_WIN
        and FROZEN
        and "--no-install" not in sys.argv
        and not (base / "Font").exists()
        and not _is_admin()
        and _same_path(base, _install_dir())
    ):
        _run_elevated(sys.executable, subprocess.list2cmdline(["--make-font-dir", str(base / "Font")]))
    for d in (base / "Font", APP_DIR / "Font"):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("x")
            probe.unlink()
            return d
        except Exception:
            continue
    return APP_DIR


FONT_DIR = _resolve_font_dir()
FONT_EXTS = (".ttf", ".otf", ".ttc")
GF_META = "https://fonts.google.com/metadata/fonts"
GF_CSS = "https://fonts.googleapis.com/css"

DEFAULT_FAMILY = "Segoe UI" if IS_WIN else "Sans Serif"
API = "https://lrclib.net/api"
UA = "LyricsHUD/2.0 (desktop lyrics widget)"
