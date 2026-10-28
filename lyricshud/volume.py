import time

from lyricshud.utils import clamp


class VolumeControl:
    def __init__(self):
        self.iface = None
        self.meter = None
        self.available = False
        self.app = ""
        self.per_app = True
        self.t_app = None
        self.t_cache = []
        self.t_until = 0.0
        self.connect()

    def connect(self):
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            from ctypes import cast, POINTER

            dev = AudioUtilities.GetSpeakers()
            iface = getattr(dev, "EndpointVolume", None)
            if iface is None:
                raw = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                iface = cast(raw, POINTER(IAudioEndpointVolume))
            self.iface = iface
            iface.GetMasterVolumeLevelScalar()
            self.available = True
            try:
                from pycaw.pycaw import IAudioMeterInformation

                raw_dev = getattr(dev, "_dev", dev)
                mraw = raw_dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                self.meter = cast(mraw, POINTER(IAudioMeterInformation))
            except Exception:
                self.meter = None
        except Exception:
            self.iface = None
            self.available = False

    def peak(self):
        if self.meter is None:
            return None
        try:
            return float(self.meter.GetPeakValue())
        except Exception:
            return None

    def targets(self):
        app = (self.app or "").lower()
        if not app or not self.per_app:
            return []
        now = time.monotonic()
        if app == self.t_app and now < self.t_until:
            return self.t_cache
        keys = set()
        for part in app.split("!"):
            part = part.strip()
            if part.endswith(".exe"):
                part = part[:-4]
            if part:
                keys.add(part)
        out = []
        try:
            from pycaw.pycaw import AudioUtilities

            for sess in AudioUtilities.GetAllSessions():
                pr = getattr(sess, "Process", None)
                if pr is None:
                    continue
                try:
                    name = pr.name().lower()
                except Exception:
                    continue
                if name.endswith(".exe"):
                    name = name[:-4]
                if name and any(name == k or name in k or k in name for k in keys):
                    out.append(sess.SimpleAudioVolume)
        except Exception:
            return []
        self.t_app = app
        self.t_cache = out
        self.t_until = now + 3.0
        return out

    def get(self):
        if not self.available:
            return None
        t = self.targets()
        if t:
            try:
                return max(float(x.GetMasterVolume()) for x in t), all(bool(x.GetMute()) for x in t)
            except Exception:
                self.t_until = 0.0
        for _ in range(2):
            try:
                return float(self.iface.GetMasterVolumeLevelScalar()), bool(self.iface.GetMute())
            except Exception:
                self.connect()
                if not self.available:
                    return None
        return None

    def set(self, v):
        if not self.available:
            return
        t = self.targets()
        if t:
            try:
                for x in t:
                    x.SetMasterVolume(float(clamp(v, 0.0, 1.0)), None)
                    if v > 0:
                        x.SetMute(0, None)
                return
            except Exception:
                self.t_until = 0.0
        try:
            self.iface.SetMasterVolumeLevelScalar(float(clamp(v, 0.0, 1.0)), None)
            if v > 0:
                self.iface.SetMute(0, None)
        except Exception:
            self.connect()

    def set_mute(self, m):
        if not self.available:
            return
        t = self.targets()
        if t:
            try:
                for x in t:
                    x.SetMute(1 if m else 0, None)
                return
            except Exception:
                self.t_until = 0.0
        try:
            self.iface.SetMute(1 if m else 0, None)
        except Exception:
            self.connect()
