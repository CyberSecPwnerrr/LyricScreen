import os
import re
import hashlib
import base64
from pathlib import Path

from lyricshud.paths import ASSET_DIR, FONT_DIR


IMG_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
AUDIO_FILTER = "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.wma *.aac)"

PATH_KEYS = (
    "font_path",
    "bg_image",
    "menu_image",
    "launch_audio",
    "text_image",
    "clock_bg_image",
    "welcome_pic",
    "welcome_bg_image",
    "monitor_bg_image",
    "eq_bg_image",
    "stats_bg_image",
)
ASSET_KEYS = (
    "font_path",
    "bg_image",
    "menu_image",
    "text_image",
    "clock_bg_image",
    "welcome_pic",
    "welcome_bg_image",
    "monitor_bg_image",
    "eq_bg_image",
    "stats_bg_image",
)


def pack_assets(d, limit):
    out = {}
    skipped = []
    total = 0
    for k in ASSET_KEYS:
        p = d.get(k)
        if not p or not isinstance(p, str) or not os.path.isfile(p):
            continue
        try:
            raw = Path(p).read_bytes()
        except OSError:
            continue
        if limit is not None and total + len(raw) > limit:
            skipped.append(k)
            continue
        total += len(raw)
        out[k] = {"n": Path(p).name, "d": base64.b64encode(raw).decode("ascii")}
    return out, skipped


def unpack_assets(packed, data):
    for k, v in packed.items():
        if k not in ASSET_KEYS or not isinstance(v, dict):
            continue
        try:
            raw = base64.b64decode(str(v.get("d", "")))
        except Exception:
            continue
        name = re.sub(r"[^A-Za-z0-9._-]", "_", str(v.get("n", "file")))[-80:] or "file"
        if not raw or len(raw) > 50000000:
            continue
        folder = FONT_DIR if k == "font_path" else ASSET_DIR
        dest = folder / (hashlib.md5(raw).hexdigest()[:8] + "_" + name)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(raw)
        except OSError:
            continue
        data[k] = str(dest)


LOCAL_KEYS = (
    "hud_x",
    "hud_y",
    "hud_w",
    "hud_h",
    "clock_x",
    "clock_y",
    "monitor_x",
    "monitor_y",
    "eq_x",
    "eq_y",
    "stats_x",
    "stats_y",
    "startup",
    "hk_later",
    "hk_earlier",
    "hk_reset",
    "hk_snap",
    "hk_toggle",
    "hk_orbital",
    "welcomed",
)
