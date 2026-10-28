import json
import re
import time
import hashlib
from bisect import bisect_right
from urllib import request as urlrequest
from urllib import parse as urlparse
from urllib.error import URLError, HTTPError

from lyricshud.paths import API, CACHE_DIR, UA
from lyricshud.utils import clamp


class Lyrics:
    def __init__(self, pairs):
        self.times = [t for t, _ in pairs]
        self.texts = [x for _, x in pairs]
        self.est = [0.5 + len(x) * 0.07 if x else 0.0 for x in self.texts]
        self.caps = []
        for x in self.texts:
            if x:
                units = max(len(x.split()), len(x) / 5.5)
                self.caps.append(clamp(1.3 + 0.4 * units, 2.2, 9.0))
            else:
                self.caps.append(0.0)

    def sing(self, i):
        est = self.est[i]
        if i + 1 < len(self.times):
            gap = self.times[i + 1] - self.times[i]
            return max(0.45, min(gap * 0.92, max(est * 2.2, 3.0)))
        return max(0.45, est * 1.5)

    def index_at(self, t):
        return bisect_right(self.times, t) - 1

    def span(self, i, hold):
        s = self.times[i]
        nxt = self.times[i + 1] if i + 1 < len(self.times) else s + 9.0
        return s, min(nxt, s + self.caps[i] * hold)


TS_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
WORD_RE = re.compile(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>")
OFFSET_RE = re.compile(r"^\[offset:\s*([+-]?\d+)\]", re.I)


def parse_lrc(text):
    pairs = []
    offset = 0.0
    for raw in text.splitlines():
        raw = raw.strip()
        mo = OFFSET_RE.match(raw)
        if mo:
            offset = int(mo.group(1)) / 1000.0
            continue
        pos = 0
        stamps = []
        while True:
            m = TS_RE.match(raw, pos)
            if not m:
                break
            frac = m.group(3)
            sec = int(m.group(1)) * 60 + int(m.group(2))
            if frac:
                sec += int(frac) / (10 ** len(frac))
            stamps.append(sec)
            pos = m.end()
        if not stamps:
            continue
        body = WORD_RE.sub("", raw[pos:]).strip()
        if not body.strip("♪♫ -–—…"):
            body = ""
        for s in stamps:
            pairs.append((s - offset, body))
    if len(pairs) < 2 or not any(b for _, b in pairs):
        return None
    pairs.sort(key=lambda x: x[0])
    return Lyrics(pairs)


class NetError(Exception):
    pass


def http_json(path, params):
    url = f"{API}/{path}?{urlparse.urlencode(params)}"
    req = urlrequest.Request(url, headers={"User-Agent": UA})
    try:
        with urlrequest.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return None
        raise NetError(str(e))
    except (URLError, TimeoutError, ValueError, OSError) as e:
        raise NetError(str(e))


def clean_title(t):
    t = re.sub(
        r"\s*[\(\[][^\)\]]*(feat|ft\.|remaster|live|version|edit|mix|deluxe|bonus|mono|stereo|acoustic|radio|explicit|official|video|audio|lyrics)[^\)\]]*[\)\]]",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+-\s+.*(remaster|version|edit|mix|live|mono|stereo|deluxe|single).*$", "", t, flags=re.I)
    return t.strip() or t


def clean_artist(a):
    a = re.sub(r"\s*-\s*topic$", "", a, flags=re.I)
    a = re.split(r"\s*(?:,|&|;|\sfeat\.?\s|\sft\.?\s|\sx\s)\s*", a, flags=re.I)[0]
    return a.strip()


def pick_best(items, dur, album=""):
    cands = [i for i in items if isinstance(i, dict) and i.get("syncedLyrics")]
    if not cands:
        return None
    al = (album or "").strip().lower()

    def gap(i):
        d = i.get("duration") or 0
        return abs(d - dur) if d else 6.0

    def score(i):
        s = gap(i) if dur > 0 else 0.0
        if al and str(i.get("albumName") or "").strip().lower() != al:
            s += 0.8
        return s

    cands.sort(key=score)
    if dur > 0 and gap(cands[0]) > 12:
        return None
    return cands[0]


def cache_file(title, artist, dur):
    h = hashlib.sha1(f"{artist.lower()}|{title.lower()}|{int(round(dur))}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.json"


def fetch_lyrics(title, artist, album, dur):
    cf = cache_file(title, artist, dur)
    try:
        cached = json.loads(cf.read_text("utf-8"))
        if cached.get("synced"):
            return parse_lrc(cached["synced"])
        if time.time() - cached.get("ts", 0) < 86400:
            return None
    except Exception:
        pass

    ct = clean_title(title)
    ca = clean_artist(artist)
    failed = False
    found = None
    cands = []
    dval = int(round(dur)) if dur > 0 else None

    def get_params(t, a, al):
        p = {"track_name": t, "artist_name": a}
        if al:
            p["album_name"] = al
        if dval:
            p["duration"] = dval
        return p

    attempts = [
        ("get", get_params(title, artist, album)),
        ("get", get_params(ct, ca, album)),
        ("get", get_params(ct, ca, "")),
        ("search", {"track_name": ct, "artist_name": ca}),
        ("search", {"q": f"{ca} {ct}"}),
    ]
    seen = set()
    for path, params in attempts:
        key = (path, tuple(sorted(params.items())))
        if key in seen:
            continue
        seen.add(key)
        try:
            data = http_json(path, params)
        except NetError:
            failed = True
            continue
        if not data:
            continue
        if path == "get":
            if isinstance(data, dict) and data.get("syncedLyrics"):
                cands.append(data)
        elif isinstance(data, list):
            cands.extend(i for i in data if isinstance(i, dict) and i.get("syncedLyrics"))
        best = pick_best(cands, dur, album)
        if best is not None and (dur <= 0 or abs((best.get("duration") or 0) - dur) <= 1.5):
            break

    found = pick_best(cands, dur, album)
    if found:
        try:
            cf.write_text(json.dumps({"synced": found["syncedLyrics"], "ts": time.time()}), "utf-8")
        except Exception:
            pass
        return parse_lrc(found["syncedLyrics"])
    if not failed:
        try:
            cf.write_text(json.dumps({"synced": None, "ts": time.time()}), "utf-8")
        except Exception:
            pass
    return None
