import sys


IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

if not (IS_WIN or IS_LINUX):
    print("Lyrics HUD needs Windows or Linux.")
    sys.exit(1)

import os
import subprocess
import importlib
import warnings
import ctypes
from ctypes import wintypes
from pathlib import Path


warnings.filterwarnings("ignore", category=FutureWarning)

os.environ["QT_LOGGING_RULES"] = "qt.multimedia.*=false;qt.multimedia.ffmpeg.*=false;qt.multimedia.ffmpeg=false"
os.environ.setdefault("QT_FFMPEG_DEBUG", "0")

if IS_WIN:
    REQUIRED = [
        ("PyQt6", "PyQt6"),
        ("winrt.runtime", "winrt-runtime"),
        ("winrt.windows.foundation", "winrt-Windows.Foundation"),
        ("winrt.windows.foundation.collections", "winrt-Windows.Foundation.Collections"),
        ("winrt.windows.media", "winrt-Windows.Media"),
        ("winrt.windows.media.control", "winrt-Windows.Media.Control"),
        ("winrt.windows.storage.streams", "winrt-Windows.Storage.Streams"),
    ]
    OPTIONAL = [("comtypes", "comtypes"), ("pycaw", "pycaw"), ("PIL", "pillow"), ("psutil", "psutil")]
else:
    REQUIRED = [("PyQt6", "PyQt6"), ("jeepney", "jeepney")]
    OPTIONAL = [("PIL", "pillow"), ("psutil", "psutil")]


def ensure_packages():
    missing = []
    for mod, pkg in REQUIRED:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    if missing:
        print("Installing:", ", ".join(missing))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing]
        )
    for mod, pkg in OPTIONAL:
        try:
            importlib.import_module(mod)
        except Exception:
            print("Installing optional:", pkg)
            subprocess.call(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    importlib.invalidate_caches()


APP_NAME = "Lyrics Screen"
EXE_NAME = "LyricsScreen.exe"
FROZEN = bool(getattr(sys, "frozen", False))


class _SEI(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _msgbox(text):
    try:
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
    except Exception:
        pass


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _install_dir():
    base = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    return Path(base) / APP_NAME


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _clean_env():
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_MEIPASS2", None)
    return env


def _do_copy(src, dst_dir):
    import shutil

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        tmp = dst_dir / (EXE_NAME + ".new")
        shutil.copy2(str(src), str(tmp))
        os.replace(str(tmp), str(dst_dir / EXE_NAME))
        return 0
    except Exception:
        return 1


def _run_elevated(exe, params):
    k = ctypes.windll.kernel32
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    ctypes.windll.shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SEI)]
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    os.environ.pop("_MEIPASS2", None)
    sei = _SEI()
    sei.cbSize = ctypes.sizeof(_SEI)
    sei.fMask = 0x00000040
    sei.lpVerb = "runas"
    sei.lpFile = exe
    sei.lpParameters = params
    sei.nShow = 0
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return None
    k.WaitForSingleObject(sei.hProcess, 180000)
    code = wintypes.DWORD(1)
    k.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
    k.CloseHandle(sei.hProcess)
    return int(code.value)


def _make_desktop_shortcut(target):
    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d ($env:LH_NAME+'.lnk')));"
        "$s.TargetPath=$env:LH_EXE;"
        "$s.WorkingDirectory=Split-Path $env:LH_EXE;"
        "$s.IconLocation=$env:LH_EXE;"
        "$s.Description=$env:LH_NAME;"
        "$s.Save()"
    )
    env = dict(os.environ, LH_NAME=APP_NAME, LH_EXE=str(target))
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env,
            creationflags=0x08000000,
            timeout=60,
            check=False,
        )
    except Exception:
        pass


def _make_font_dir(d):
    try:
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["icacls", str(d), "/grant", "*S-1-5-32-545:(OI)(CI)M"],
            creationflags=0x08000000,
            timeout=30,
            check=False,
        )
        return 0
    except Exception:
        return 1


def self_install():
    if not FROZEN or not IS_WIN or "--no-install" in sys.argv:
        return
    if "--install-copy" in sys.argv:
        i = sys.argv.index("--install-copy")
        sys.exit(_do_copy(Path(sys.argv[i + 1]), Path(sys.argv[i + 2])))
    if "--make-font-dir" in sys.argv:
        i = sys.argv.index("--make-font-dir")
        sys.exit(_make_font_dir(Path(sys.argv[i + 1])))
    exe = Path(sys.executable)
    target_dir = _install_dir()
    target = target_dir / EXE_NAME
    if _same_path(exe.parent, target_dir):
        return
    import filecmp

    try:
        up_to_date = target.exists() and filecmp.cmp(str(exe), str(target), shallow=False)
    except Exception:
        up_to_date = False
    if not up_to_date:
        if _is_admin():
            code = _do_copy(exe, target_dir)
        else:
            code = _run_elevated(str(exe), subprocess.list2cmdline(["--install-copy", str(exe), str(target_dir)]))
        if code is None:
            return
        if code != 0 or not target.exists():
            _msgbox(
                "Could not install to:\n" + str(target_dir) + "\n\n"
                "If Lyrics Screen is already running, quit it from the tray icon and open this file again."
            )
            sys.exit(1)
    _make_desktop_shortcut(target)
    try:
        subprocess.Popen(
            [str(target)],
            cwd=str(target_dir),
            env=_clean_env(),
            close_fds=True,
            creationflags=0x00000008 | 0x00000200,
        )
    except Exception as e:
        _msgbox("Installed, but could not start the app:\n" + str(e))
        sys.exit(1)
    sys.exit(0)


self_install()
if not FROZEN:
    ensure_packages()
