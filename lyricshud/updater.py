import sys
import os
import json
import re
import zipfile
import shutil
import threading
import subprocess
from urllib import request as urlrequest

from PyQt6.QtCore import QObject, pyqtSignal

from lyricshud.boot import IS_LINUX
from lyricshud.paths import APP_VERSION, REPO_DEFAULT, UPDATE_DIR
from lyricshud.utils import open_path


class Updater(QObject):
    status = pyqtSignal(str)
    final = pyqtSignal(str)
    ready = pyqtSignal(str, str)

    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.busy = False
        self.last = "Not checked yet"
        self.status.connect(self.remember)
        self.ready.connect(self.install)

    def remember(self, t):
        self.last = t

    def finish(self, t):
        self.status.emit(t)
        self.final.emit(t)

    @staticmethod
    def ver(text):
        nums = [int(n) for n in re.findall(r"\d+", str(text))[:4]]
        while len(nums) < 4:
            nums.append(0)
        return tuple(nums)

    def check(self):
        if self.busy:
            return
        repo = self.ctl.cfg["update_repo"].strip().strip("/") or REPO_DEFAULT
        if repo.startswith("https://github.com/"):
            repo = repo[len("https://github.com/"):]
        if repo.count("/") != 1:
            self.finish("Enter the GitHub repository as owner/repo first")
            return
        self.busy = True
        self.status.emit("Checking for updates...")
        threading.Thread(target=self.run, args=(repo,), daemon=True).start()

    def get(self, url, accept):
        req = urlrequest.Request(url, headers={"User-Agent": "LyricsHUD-Updater", "Accept": accept})
        return urlrequest.urlopen(req, timeout=30)

    def run(self, repo):
        try:
            with self.get(f"https://api.github.com/repos/{repo}/releases/latest", "application/vnd.github+json") as r:
                data = json.loads(r.read().decode("utf-8"))
            tag = str(data.get("tag_name", ""))
            if self.ver(tag) <= self.ver(APP_VERSION):
                self.finish(f"You are on the latest version (v{APP_VERSION})")
                return
            assets = [a for a in data.get("assets", []) if isinstance(a, dict)]
            pick = None
            for ext in (".appimage",) if IS_LINUX else (".zip", ".exe"):
                for a in assets:
                    if str(a.get("name", "")).lower().endswith(ext):
                        pick = a
                        break
                if pick:
                    break
            if pick is None:
                self.finish(f"{tag} has no {'AppImage' if IS_LINUX else 'zip or exe'} to download")
                return
            name = re.sub(r"[^A-Za-z0-9._-]", "_", str(pick["name"]))
            dest = UPDATE_DIR / name
            with self.get(str(pick["browser_download_url"]), "application/octet-stream") as r, open(dest, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                last = -1
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        pct = int(got * 100 / total)
                        if pct // 5 != last:
                            last = pct // 5
                            self.status.emit(f"Downloading {tag}... {pct}%")
            exe = dest
            if name.lower().endswith(".zip"):
                out = UPDATE_DIR / ("v" + re.sub(r"[^A-Za-z0-9._-]", "_", tag))
                if out.exists():
                    shutil.rmtree(out, ignore_errors=True)
                with zipfile.ZipFile(dest) as z:
                    z.extractall(out)
                exes = [x for x in out.rglob("*.exe") if "unins" not in x.name.lower()]
                if not exes:
                    self.finish("The zip does not contain an exe")
                    return
                exe = max(exes, key=lambda x: x.stat().st_size)
            self.ready.emit(str(exe), tag)
        except Exception as e:
            self.finish("Update check failed: " + str(e))
        finally:
            self.busy = False

    def install(self, exe, tag):
        if IS_LINUX:
            target = os.environ.get("APPIMAGE")
            if target and os.path.isfile(target):
                try:
                    tmp = target + ".new"
                    shutil.copy2(exe, tmp)
                    os.chmod(tmp, 0o755)
                    os.replace(tmp, target)
                    subprocess.Popen([target], start_new_session=True, close_fds=True)
                    self.finish(f"Installed {tag} and restarting...")
                    self.ctl.app.quit()
                except OSError as e:
                    self.finish("Could not install the update: " + str(e))
                return
            try:
                os.chmod(exe, 0o755)
            except OSError:
                pass
            self.finish(f"Downloaded {tag} to {exe}")
            return
        if getattr(sys, "frozen", False):
            cur = sys.executable
            bat = UPDATE_DIR / "apply_update.bat"
            bat.write_text(
                "@echo off\r\n"
                f'set "NEW={exe}"\r\n'
                f'set "OLD={cur}"\r\n'
                "for /l %%i in (1,1,40) do (\r\n"
                '  copy /Y "%NEW%" "%OLD%" >nul 2>&1 && goto ok\r\n'
                "  ping -n 2 127.0.0.1 >nul\r\n"
                ")\r\n"
                ":ok\r\n"
                'start "" "%OLD%"\r\n'
                'del "%~f0"\r\n',
                "utf-8",
            )
            self.finish(f"Installing {tag} and restarting...")
            subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x08000000 | 0x00000008, close_fds=True)
            self.ctl.app.quit()
        else:
            try:
                open_path(exe)
                self.finish(f"Downloaded {tag} and opened it")
            except OSError as e:
                self.finish("Could not open the update: " + str(e))
