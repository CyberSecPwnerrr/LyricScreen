# 🎵 Lyrics HUD

A Windows desktop widget that shows **live, time-synced lyrics** for whatever you're playing, as a neon player card, as floating lyrics on your desktop, or both.

It reads the Windows media session directly, so it works with Spotify, YouTube Music in the browser and other players. No client ID, API key or login needed.

> by **CyberSecPwner**

---

## ✨ Features

- **Synced lyrics** fetched from [LRCLIB](https://lrclib.net) and cached locally
- **Three display modes**: Player card, Floating lyrics, or Card + floating lyrics
- **Player card** with cover art, title, artist, album, progress bar, volume and an EQ visualizer
- **Floating lyrics** that can sit on the desktop wallpaper layer or on top of windows
- **Adaptive colors** pulled from the current album cover
- **Karaoke-style** line highlighting with adjustable anticipation
- **Visual effects**: particles, scanlines, glitch, tilt, glow, ghost lines
- **Entry animations**: Classic slide, Rise, Zoom, Fade only
- **Flexible placement**: random or fixed positions (top/middle/bottom, left/right)
- **Sync tools**: per-track offsets, auto-sync, and "snap" sync from the tray menu or hotkeys
- **Click-through lock**, system tray control, global hotkeys
- **Full settings UI** for fonts, colors, weight, spacing, outline, shadow, opacity, FPS and more

---

## 📋 Requirements

- **Windows 10 / 11** (uses the Windows media session API; the script exits on other systems)
- **Python 3.9+**

Dependencies are installed automatically on first launch:

| Package | Purpose |
|---|---|
| `PyQt6` | UI and rendering |
| `winrt-runtime`, `winrt-Windows.Foundation`, `winrt-Windows.Foundation.Collections`, `winrt-Windows.Media`, `winrt-Windows.Media.Control`, `winrt-Windows.Storage.Streams` | Windows media session access |
| `comtypes`, `pycaw` *(optional)* | System volume control and display |

---

## 🚀 Getting Started

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
python lyrics_hud.py
```

Start playing music and the HUD appears. A **♪ tray icon** gives you control of everything.

> **Browsers:** hardware media control must be enabled. It is on by default in Chrome, Brave and Edge.

---

## 🎮 Controls

### Mouse

| Action | Result |
|---|---|
| Click the progress bar | Seek |
| Scroll over the card | Change volume |
| Right-click the card | Quick menu |
| Click the tray icon | Show / hide |

### Global hotkeys

All hotkeys use **Ctrl + Alt + Shift**:

| Key | Action |
|---|---|
| `J` | Lyrics later (−100 ms) |
| `K` | Lyrics earlier (+100 ms) |
| `H` | Reset sync offset |
| `N` | Next line starts now (snap sync) |
| `V` | Show / hide |

Hotkeys can be turned off in the settings.

### Tray menu

Play / pause, next / previous track, show / hide, display mode, lock card in place, sync adjustments, settings, reset card position, quit.

---

## ⚙️ Settings

Open **Settings** from the tray menu. Pages:

- **Appearance**: colors, fonts, glow, opacity, effects
- **Lyrics**: size, weight, spacing, case, fill, outline, shadow, animation, placement
- **Overlay**: floating lyrics layout, screen, scale, wallpaper layer and blending
- **Player**: card options (cover, volume, album, status, EQ, toast)
- **About**: quick usage notes

---

## 📁 Data & Privacy

Everything is stored locally in `%APPDATA%\LyricsHUD\`:

| File | Content |
|---|---|
| `config.json` | Your settings |
| `track_offsets.json` | Per-track sync offsets |
| `cache/` | Cached lyrics |

The only network requests go to the public **LRCLIB** API to look up lyrics for the current track.

---

## 🛠️ Troubleshooting

- **No lyrics showing**: the track may not have synced lyrics on LRCLIB.
- **Nothing detected**: make sure your player shows up in the Windows media overlay (volume flyout), and that browser media control is enabled.
- **Lyrics out of sync**: use the hotkeys (`J` / `K`) or the tray's "Sync: current line starts now" options.
- **Card lost off-screen**: tray menu → *Reset card position*.

---

## 🙏 Credits

- Lyrics provided by [LRCLIB](https://lrclib.net)
- Built with [PyQt6](https://pypi.org/project/PyQt6/) and [winrt](https://pypi.org/project/winrt-runtime/)

## 📄 License

Add a license of your choice (e.g. MIT) before publishing.
