![LyricsScreen Banner](assets/banner.png)

<div align="center">

# 🎵 Lyrics HUD — LyricsScreen

**Live, time-synced lyrics for your Windows desktop.**

A customizable music player card and floating karaoke lyrics overlay that brings your music to life.

**Works with any music app** that exposes playback information through the Windows media session API, including Spotify, YouTube Music, and other desktop or browser-based players. Lyrics will display as long as a suitable synchronized version of the song's lyrics is available in the LRCLIB library.

**Built by [CyberSecPwner](https://github.com/CyberSecPwnerrr)**

[Features](#-features) · [Getting Started](#-getting-started) · [Controls](#-controls) · [Troubleshooting](#-troubleshooting)

</div>
<p align="center">
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases">
    <img src="assets/download.png" alt="Download LyricsScreen" width="600">
  </a>
</p>
---

## ✨ Features

- 🎤 **Synced lyrics** — fetched from [LRCLIB](https://lrclib.net) and cached locally.
- 🎵 **Works with any music app** — supports any player that exposes playback information through the Windows media session API, provided the song has suitable synchronized lyrics in LRCLIB.
- 🖥️ **Three display modes** — Player card, Floating lyrics, or Card + floating lyrics.
- 🎵 **Music player card** — album artwork, title, artist, album, progress bar, volume control, and EQ visualizer.
- 🪟 **Floating lyrics overlay** — display lyrics on the desktop wallpaper layer or above other windows.
- 🎨 **Adaptive colors** — colors derived from the current album artwork.
- 🎙️ **Karaoke highlighting** — current lyric line highlighting with adjustable anticipation.
- 🌌 **Visual effects** — particles, scanlines, glitch, tilt, glow, and ghost lines.
- 🎬 **Entry animations** — Classic slide, Rise, Zoom, and Fade.
- 📍 **Flexible placement** — random or fixed positions, including top, middle, bottom, left, and right.
- ⏱️ **Sync tools** — per-track offsets, auto-sync, and snap sync through the tray menu or hotkeys.
- 🖱️ **Click-through lock** — interact with windows beneath the floating overlay when enabled.
- 🎛️ **System tray controls** — manage playback, display modes, synchronization, and settings.
- ⌨️ **Global hotkeys** — adjust synchronization and show or hide the HUD.
- ⚙️ **Extensive customization** — fonts, colors, weight, spacing, outlines, shadows, opacity, FPS, and more.

---

## 📸 Display Modes

### Player Card

A compact, customizable music player card with album artwork, track metadata, playback progress, volume, and a visualizer.

### Floating Lyrics

A standalone lyrics overlay that can sit on the desktop wallpaper layer or remain above other windows.

### Card + Floating Lyrics

Combine the player card and floating lyrics for a complete desktop music experience.

---

## 📋 Requirements

- **Operating system:** Windows 10 or Windows 11.
- **Python:** Python 3.9 or newer, required only when running from source.
- **Internet connection:** Required to retrieve lyrics from LRCLIB when they are not cached.
- **Music app:** Any music player that exposes playback information through the Windows media session API.
- **Lyrics availability:** The song must have a suitable synchronized lyrics entry in LRCLIB for lyrics to be displayed.

---

## 🚀 Getting Started

### Option 1: Run the executable (no Python required)

Want the easy way? Simply download and open the prebuilt `.exe` file. **You do not need to install Python or any dependencies.**

1. Open the [LyricsScreen Releases](https://github.com/CyberSecPwnerrr/LyricScreen/releases) page.
2. Download the latest Windows executable, if a release is available.
3. Open the downloaded `.exe` file.
4. Start playing music in your preferred music app.

LyricsScreen will detect the active Windows media session when supported playback information is available. It can work with different music apps, provided they expose the required media information and the song has suitable synchronized lyrics available in LRCLIB.

> **Note:** A downloadable executable must first be published in the GitHub Releases section. If no release is available yet, use Option 2.

### Option 2: Run from source using Python

#### 1. Install Python

Install Python 3.9 or newer if it is not already installed.

#### 2. Clone the repository

```bash
git clone https://github.com/CyberSecPwnerrr/LyricScreen.git
cd LyricScreen
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Launch LyricsScreen

```bash
python lyrics_hud.py
```

#### 5. Start playing music

Play a track in your preferred music app. A **♪ system tray icon** provides access to the application controls and settings.

> **Browser support:** Browser-based music players must expose playback information through the Windows media session API. Hardware media key and media session integration is generally enabled by default in Chrome, Brave, and Edge.

---

## 🎮 Controls

### Mouse Controls

| Action | Result |
|---|---|
| Click the progress bar | Seek through the track |
| Scroll over the player card | Change volume |
| Right-click the player card | Open the quick menu |
| Click the tray icon | Show or hide the HUD |

### Global Hotkeys

All global hotkeys use **Ctrl + Alt + Shift** as the modifier combination.

| Shortcut | Action |
|---|---|
| `Ctrl + Alt + Shift + J` | Adjust lyrics later by 100 ms |
| `Ctrl + Alt + Shift + K` | Adjust lyrics earlier by 100 ms |
| `Ctrl + Alt + Shift + H` | Reset the synchronization offset |
| `Ctrl + Alt + Shift + N` | Snap the current lyric line to the current time |
| `Ctrl + Alt + Shift + V` | Show or hide the HUD |

Hotkeys can be disabled in the settings.

### System Tray Menu

The tray menu provides access to:

- Play and pause.
- Next and previous track.
- Show and hide.
- Display mode selection.
- Locking the player card in place.
- Synchronization adjustments.
- Settings.
- Resetting the card position.
- Quitting the application.

---

## ⚙️ Settings

Open **Settings** from the system tray menu.

### Appearance

Customize colors, fonts, glow, opacity, and visual effects.

### Lyrics

Configure lyric size, font weight, spacing, letter case, fill, outline, shadow, animation, and placement.

### Overlay

Customize the floating lyrics layout, display screen, scaling, wallpaper layer, and blending.

### Player

Configure the player card, including artwork, volume, album information, status, equalizer visualization, and notifications.

### About

View quick usage information.

---

## 🎤 Lyrics and Synchronization

LyricsScreen retrieves synchronized lyrics from [LRCLIB](https://lrclib.net).

Lyrics are cached locally to reduce repeated network requests.

**Lyrics compatibility:** LyricsScreen is designed to work with any music app that provides the required playback information through the Windows media session API. The music app itself does not need to be specifically supported by LyricsScreen. However, lyrics can only be displayed when a suitable synchronized entry for the current song is available in LRCLIB.

If lyrics are out of sync, use the global hotkeys or synchronization controls in the tray menu.

- **Fine adjustment:** Shift lyrics in 100 ms increments.
- **Reset:** Restore the default synchronization offset.
- **Snap sync:** Align the current lyric line with the current playback position.
- **Per-track offsets:** Keep individual timing adjustments for specific tracks.

Lyric availability depends on whether LRCLIB has a suitable synchronized entry for the current track.

---

## 📁 Data & Privacy

LyricsScreen stores its configuration and cached data locally in:

```text
%APPDATA%\LyricsHUD\
```

| File or directory | Purpose |
|---|---|
| `config.json` | Application settings |
| `track_offsets.json` | Per-track synchronization offsets |
| `cache/` | Cached lyrics |

The application uses the public LRCLIB API to look up lyrics for the current track. An internet connection is needed when the required lyrics are not available in the local cache.

---

## 🛠️ Troubleshooting

### No lyrics are showing

- Check whether synchronized lyrics are available on LRCLIB.
- Confirm that the current track's title and artist are detected correctly.
- Check your internet connection if the lyrics have not been cached.

### No media is detected

- Make sure the player appears in the Windows volume flyout media controls.
- Enable browser hardware media control if using a browser-based player.
- Try playing or pausing the track to refresh the media session.
- Verify that the music app exposes playback information through the Windows media session API.

### Lyrics are out of sync

- Use `Ctrl + Alt + Shift + J` or `Ctrl + Alt + Shift + K` for fine adjustments.
- Use the snap-sync hotkey to align the current lyric line.
- Reset the offset if the timing becomes incorrect.

### The player card is off-screen

Open the system tray menu and select **Reset card position**.

### Dependencies fail to install

Verify that Python 3.9 or newer is installed, then update pip:

```bash
python -m pip install --upgrade pip
```

Retry installation:

```bash
pip install -r requirements.txt
```

### The application does not launch

When running from source, launch it from a terminal to inspect any error messages:

```bash
python lyrics_hud.py
```

If using the executable, check whether Windows Security has blocked it and ensure you downloaded it from the official repository.

---

## 🙏 Credits

- [LRCLIB](https://lrclib.net) — synchronized lyrics API.
- [PyQt6](https://pypi.org/project/PyQt6/) — graphical user interface.
- [WinRT for Python](https://pypi.org/project/winrt-runtime/) — Windows Runtime integration.

<div align="center">

**LyricsScreen — Your music. Your lyrics. Your desktop.**

Made with 🎵 by [CyberSecPwner](https://github.com/CyberSecPwnerrr)

</div>
