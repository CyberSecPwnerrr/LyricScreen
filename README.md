<div align="center">

  <img src="assets/banner.png" alt="LyricsScreen banner" width="100%">

  # LyricsScreen

  **Live, time-synced lyrics and a customizable music HUD for Windows.**

  Works with compatible music players through the Windows media session API.

  <p>
    <a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases">
      <img src="https://img.shields.io/badge/Download-Latest%20Release-2f81f7?style=for-the-badge&logo=github&logoColor=white" alt="Download latest release">
    </a>
    <a href="https://github.com/CyberSecPwnerrr/LyricScreen">
      <img src="https://img.shields.io/github/stars/CyberSecPwnerrr/LyricScreen?style=for-the-badge&logo=github&label=Stars" alt="GitHub stars">
    </a>
    <a href="https://github.com/CyberSecPwnerrr/LyricScreen">
      <img src="https://img.shields.io/github/downloads/CyberSecPwnerrr/LyricScreen/total?style=for-the-badge&logo=github&logoColor=white&label=Downloads&color=2f81f7" alt="Total GitHub downloads">
    </a>
  </p>

  <p>
    <a href="#features">Features</a> ·
    <a href="#screenshots-and-display-modes">Display modes</a> ·
    <a href="#installation">Installation</a> ·
    <a href="#controls">Controls</a> ·
    <a href="#troubleshooting">Troubleshooting</a>
  </p>

</div>

---

## What is LyricsScreen?

LyricsScreen puts your music controls and synchronized lyrics directly on your desktop. Use a compact player card, a floating karaoke overlay, or both together. You can customize the appearance, animations, colors, and position to fit your desktop.

It reads playback information from the Windows media session API, so it can work with compatible apps such as Spotify, YouTube Music, and browser-based players. Synchronized lyrics are fetched from [LRCLIB](https://lrclib.net).

## Features

- **Synchronized lyrics** — timed lyrics with current-line highlighting, anticipation, and per-track timing offsets.
- **Player card** — album art, track details, progress, volume, playback status, and an equalizer.
- **Floating lyrics** — place lyrics above your desktop or on the wallpaper layer.
- **Live clock** — draggable clock with configurable date, time format, size, opacity, and background.
- **Themes** — Cyber Neon, Frosted Glass, Aurora, Synthwave, Midnight, Sakura, Ember, Emerald, Crystal, and more.
- **Customization** — colors, gradients, fonts, blur, transparency, borders, shadows, glow, and card layout.
- **Animations and effects** — lyric transitions, scanlines, glitch effects, flicker, and 3D tilt.
- **Multiple monitors** — choose the display for the floating lyrics.
- **Quick controls** — system tray menu, global hotkeys, and Quick Customize.
- **Profiles and share codes** — save settings or share most non-file-based customization.
- **Optional extras** — Google Fonts search, launch audio, welcome screen, and automatic update checks.

## Screenshots and display modes

### Player card
A desktop music card showing album artwork, track information, playback progress, volume, and visualizer.

### Floating lyrics
A standalone karaoke-style overlay with adjustable position, size, colors, and animation.

### Card + floating lyrics
Use the player card and lyrics overlay together. Each can be customized independently.

### Live clock
An optional draggable clock that follows the application's theme.

> Add screenshots to the repository and link them here when ready. For example: `![Player card](assets/player-card.png)`

## Installation

### Option 1: Download the Windows release

1. Open the [GitHub Releases](https://github.com/CyberSecPwnerrr/LyricScreen/releases) page.
2. Download the latest Windows executable, if a release is available.
3. Run it and follow any Windows prompts.
4. Start playing music in a supported player.

The packaged executable includes the dependencies needed to run the application.

### Option 2: Run from source

**Requirements:** Windows 10 or 11 and Python 3.9 or newer.

```bash
git clone https://github.com/CyberSecPwnerrr/LyricScreen.git
cd LyricScreen
python lyrics_hud.py
```

When launched from source, LyricsScreen checks for and installs its required Python packages.

## Compatibility

LyricsScreen uses the Windows media session API to detect playback. The player must expose its current media session to Windows. Browser-based players may require hardware media controls to be enabled.

Lyrics are provided by LRCLIB. A track needs a matching synchronized-lyrics entry for lyrics to appear.

## Controls

### Mouse

| Action | Result |
|---|---|
| Click the progress bar | Seek through the track |
| Scroll over the player card | Adjust volume |
| Right-click the player card | Open the quick menu |
| Click the tray icon | Show or hide the HUD |
| Drag the clock | Move the clock |

### Global hotkeys

The default modifier is `Ctrl + Alt + Shift`.

| Shortcut | Action |
|---|---|
| `Ctrl + Alt + Shift + J` | Move lyrics earlier by 100 ms |
| `Ctrl + Alt + Shift + K` | Move lyrics later by 100 ms |
| `Ctrl + Alt + Shift + H` | Reset lyric timing |
| `Ctrl + Alt + Shift + N` | Snap the current lyric line to playback |
| `Ctrl + Alt + Shift + V` | Show or hide the HUD |

Hotkeys can be disabled in Settings. The tray menu also includes playback, display-mode, synchronization, and position controls.

## Settings

Open **Settings** from the system tray menu.

- **Appearance:** themes, colors, gradients, card styles, blur, opacity, borders, shadows, and glow.
- **Lyrics:** font, size, spacing, highlighting, anticipation, timing, and placement.
- **Animation:** entry and exit styles, idle motion, visual effects, and frame-rate limits.
- **Player card:** layout, album art, track details, volume, equalizer, and background.
- **Overlay:** display layer, monitor selection, lyric size, width, and wallpaper dimming.
- **Clock:** time format, date, size, opacity, and background.
- **Profiles:** save and load named settings profiles.
- **Share codes:** export and import most settings that do not depend on local files.

Share codes do not include custom images, downloaded fonts, or launch-audio files. Those files must be selected separately on another computer.

## Data and privacy

LyricsScreen stores its settings and cached data locally:

```text
%APPDATA%\LyricsHUD\
```

| File or folder | Purpose |
|---|---|
| `config.json` | Application settings |
| `track_offsets.json` | Per-track lyric timing |
| `cache/` | Cached lyrics |
| `profiles/` | Saved profiles |
| `Font/` | Fonts available to the application |

LyricsScreen contacts LRCLIB to look up lyrics when they are not already cached. Google Fonts search and downloads also require an internet connection.

## Troubleshooting

**No lyrics appear**
- Check whether synchronized lyrics are available for the track on LRCLIB.
- Check that the detected title and artist are correct.
- Make sure you have an internet connection if the lyrics are not cached.

**No music is detected**
- Check whether the player appears in the Windows volume flyout.
- Enable browser hardware media controls if you use a browser.
- Play or pause the track to refresh its media session.

**Lyrics are out of sync**
- Use `Ctrl + Alt + Shift + J` or `K` to adjust timing.
- Use the snap-sync shortcut to align the current line.
- Reset the offset if needed.

**The player card or clock is off-screen**
- Use the reset-position actions in the tray menu or clock settings.

**A custom image, font, or sound is missing**
- Check that the file still exists at its selected path. Share codes do not package local files.

**The application does not launch**
- If running from source, launch it in a terminal with `python lyrics_hud.py` to see error messages.
- If using the executable, check Windows Security and make sure it came from the official Releases page.

## Credits

- [LRCLIB](https://lrclib.net) — synchronized lyrics.
- [PyQt6](https://pypi.org/project/PyQt6/) — application interface.
- [WinRT for Python](https://pypi.org/project/winrt-runtime/) — Windows Runtime integration.
- [Google Fonts](https://fonts.google.com/) — font library.
 CyberSecPwner (Me)
---

<div align="center">

**LyricsScreen** · Your music, your lyrics, your desktop.

Made by [CyberSecPwner](https://github.com/CyberSecPwnerrr)

</div>
