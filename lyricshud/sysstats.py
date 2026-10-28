import os
import ctypes
from ctypes import wintypes

from lyricshud.utils import clamp


class SysStats:
    def __init__(self):
        self.ps = None
        try:
            import psutil

            self.ps = psutil
            psutil.cpu_percent(None)
        except Exception:
            self.ps = None
        self.last_times = None
        self.cache = {}
        self.ncpu = max(1, os.cpu_count() or 1)

    def cpu(self):
        if self.ps is not None:
            try:
                return float(self.ps.cpu_percent(None))
            except Exception:
                return 0.0
        try:
            idle = wintypes.FILETIME()
            kern = wintypes.FILETIME()
            user = wintypes.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))

            def val(f):
                return (f.dwHighDateTime << 32) | f.dwLowDateTime

            i, k, u = val(idle), val(kern), val(user)
            if self.last_times is None:
                self.last_times = (i, k, u)
                return 0.0
            li, lk, lu = self.last_times
            self.last_times = (i, k, u)
            total = (k - lk) + (u - lu)
            busy = total - (i - li)
            return float(clamp(100.0 * busy / total, 0.0, 100.0)) if total > 0 else 0.0
        except Exception:
            return 0.0

    def ram(self):
        if self.ps is not None:
            try:
                m = self.ps.virtual_memory()
                return float(m.used), float(m.total), float(m.percent)
            except Exception:
                pass

        class MEM(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            total = float(m.ullTotalPhys)
            used = total - float(m.ullAvailPhys)
            return used, total, float(m.dwMemoryLoad)
        except Exception:
            return 0.0, 1.0, 0.0

    def procs(self, n):
        if self.ps is None:
            return []
        rows = []
        seen = set()
        for p in self.ps.process_iter(["pid", "name"]):
            try:
                pid = p.info["pid"]
                if pid == 0:
                    continue
                seen.add(pid)
                proc = self.cache.get(pid)
                if proc is None:
                    self.cache[pid] = p
                    p.cpu_percent(None)
                    continue
                rows.append((proc.cpu_percent(None) / self.ncpu, pid, p.info["name"] or "?"))
            except Exception:
                continue
        for pid in list(self.cache):
            if pid not in seen:
                del self.cache[pid]
        rows.sort(reverse=True)
        out = []
        for cpu, pid, name in rows[:n]:
            try:
                mem = float(self.cache[pid].memory_info().rss)
            except Exception:
                mem = 0.0
            out.append((name, cpu, mem))
        return out
