import json
from pathlib import Path

from lyricshud.assets import LOCAL_KEYS, pack_assets, unpack_assets
from lyricshud.defaults import DEFAULTS
from lyricshud.paths import CFG_PATH
from lyricshud.utils import fresh_defaults


class Config:
    def __init__(self):
        self.data = fresh_defaults()
        try:
            self.apply(json.loads(CFG_PATH.read_text("utf-8")))
        except Exception:
            pass

    def apply(self, loaded, skip=()):
        for k, v in loaded.items():
            if k in skip:
                continue
            if k in DEFAULTS and (not isinstance(DEFAULTS[k], list) or isinstance(v, list)):
                self.data[k] = v

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def save(self):
        try:
            CFG_PATH.write_text(json.dumps(self.data, indent=2), "utf-8")
        except Exception:
            pass

    def snapshot(self):
        return {k: v for k, v in self.data.items() if k not in LOCAL_KEYS}

    def write_to(self, path, assets=True):
        d = self.snapshot()
        if assets:
            packed, _ = pack_assets(d, None)
            if packed:
                d["_assets"] = packed
        Path(path).write_text(json.dumps(d, indent=2), "utf-8")

    def read_from(self, path):
        data = json.loads(Path(path).read_text("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a settings file")
        packed = data.pop("_assets", None)
        if isinstance(packed, dict):
            unpack_assets(packed, data)
        self.apply(data, LOCAL_KEYS)

    def reset(self):
        keep = {k: self.data[k] for k in LOCAL_KEYS}
        self.data = fresh_defaults()
        self.data.update(keep)
