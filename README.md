![LyricsScreen Banner](assets/banner.png)

<div align="center">

# 🎵 Lyrics HUD — LyricsScreen
# 📃 LyricScreen Website
**https://lyricscreen.netlify.app**
**Live, time-synced lyrics and a customizable desktop music experience for Windows.**

A music player card, floating karaoke lyrics, live clock, custom themes, and animated desktop widgets — all in one application.

Works with music apps that expose playback information through the Windows media session API, including Spotify, YouTube Music, and supported browser-based players. Lyrics appear when a suitable synchronized version is available through LRCLIB.

[Features](#-features) · [Getting Started](#-getting-started) · [Controls](#-controls) · [Settings](#️-settings) · [Troubleshooting](#-troubleshooting)

</div>

<p align="center">
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases">
    <img src="assets/download.png" alt="Download LyricsScreen" width="600">
  </a>
</p>

<details>
<summary><strong>✨ Click Here to See What's New in V8</strong></summary>

<br>

### 🆕 What's New in V8

V8 takes LyricsScreen to the next level with more control, deeper customization, new desktop widgets, and enhanced visual effects!

- 📊 **System Performance Monitor** — Track CPU, RAM, FPS, rendering performance, and running processes directly on your desktop.
- 🎛️ **Customizable Top Bar** — A new configurable interface with animated equalizer bars, adjustable positioning, and layout options.
- 🎨 **Expanded Theme System** — Explore more visual themes, including Aurora, Frosted Glass, Crystal, Sakura, Emerald, and more.
- 🌈 **Advanced Color Modes** — New adaptive color palettes, custom lyric gradients, and additional color combinations.
- ✨ **Enhanced Lyric Animations** — More entrance and exit effects, smoother transitions, and customizable idle animations.
- 🖥️ **Desktop Wallpaper Lyrics** — Display lyrics as part of your desktop wallpaper layer, with adjustable dimming and blending.
- 🖥️ **Multi-Monitor Support** — Choose which screen displays your floating lyrics and customize their size and positioning.
- 🎚️ **Advanced Performance Controls** — Fine-tune animation FPS and optimization settings for a smoother experience.
- 🎵 **Improved Player Controls** — Better volume control, playback shortcuts, and more control over the player overlay.
- 🧊 **More Visual Customization** — Adjust card sizes, glass effects, blur, shadows, borders, glow, and transparency.
- ⌨️ **Keyboard Shortcuts** — Control playback and synchronize lyrics more conveniently.
- 🔄 **Automatic Updates** — Optional update checks to help you stay up to date.
- ⚙️ **More Settings & Fine-Tuning** — Additional options for lyric placement, synchronization, animations, interface behavior, and widgets.

**V8 is all about more control, more personalization, and a better desktop lyrics experience.**

💜 Thanks for supporting LyricsScreen! Don't forget to ⭐ star the project on GitHub and follow for future updates.

</details>

---

## ✨ Features

### Music and lyrics
- 🎤 **Synchronized lyrics** — retrieved from [LRCLIB](https://lrclib.net) and cached locally.
- 🎵 **Broad media-session support** — works with compatible players that expose playback information through the Windows media session API.
- 🖥️ **Three display modes** — Player card, Floating lyrics, or Card + floating lyrics.
- 🎵 **Customizable player card** — album artwork, title, artist, album, progress, volume, status, and equalizer visualization.
- 🎙️ **Karaoke highlighting** — current-line highlighting with adjustable anticipation and dimming for unsung text.
- ⏱️ **Sync controls** — per-track offsets, 100 ms adjustments, and snap-sync for the current or next lyric line.
- 🔔 **Now-playing notifications** — optional track-change toast showing the title and artist.

### Desktop widgets and appearance
- 🕒 **Live desktop clock** — draggable themed clock with 12/24-hour format, optional seconds and date, adjustable size and opacity, and a custom background image.
- 🎨 **Built-in themes** — Cyber Neon, Frosted Glass, Pure Minimal, Aurora, Synthwave, Midnight, Sakura, Ember, Emerald, Crystal, and Custom.
- 🌈 **Adaptive album-art colors** — choose color treatments such as vibrant, pastel, deep, complementary, triadic, analogous, and monochrome.
- 🖼️ **Custom images** — use images or animated GIFs for the player card, clock, lyrics text, and menu wallpaper where supported.
- 🪟 **Wallpaper and always-on-top layers** — put floating lyrics on the desktop wallpaper layer or above other windows.
- 🧊 **Card styling** — gradient, frosted-glass, flat, and animated aurora styles, with adjustable blur, glass, border, shadow, glow, and corner radius.
- 🌌 **Visual effects** — scanlines, glitch and chroma ghosting, flicker, glow, 3D tilt, and ghost lines.
- 🎬 **Rich lyric animations** — classic slide, rise, drop, zoom, fade, flip, bounce, stretch, swing, spin, and random entry styles, plus configurable exits and idle motion.
- 📍 **Flexible placement** — fixed or random lyric positions, adjustable overlay size and line width, and multi-monitor selection.
- 🖋️ **Font customization** — choose local fonts or search for and download fonts from Google Fonts.
- 🎚️ **Performance controls** — configurable animation frame rate and Off, Balanced, or Performance optimization modes.
- 🪟 **Fullscreen behavior** — optionally hide the card, clock, and lyrics while another app is fullscreen.
- 🖱️ **Click-through lock** — allow interaction with windows underneath the floating overlay when enabled.

### Personalization and convenience
- ⚡ **Quick Customize** — access common appearance controls without opening the full settings window.
- 🎛️ **Extensive settings** — customize lyrics, card layout, colors, typography, animation, overlays, clock, and interface behavior.
- 💾 **Settings profiles** — save and load named configuration profiles.
- 🔗 **Shareable settings codes** — export your non-file-based customization as a compact code and import a code from someone else.
- 🔊 **Launch audio** — optionally play a chosen sound when LyricsScreen starts, with volume control and a test option.
- 👋 **Welcome screen** — optional startup greeting with a preview.
- 🧭 **Customizable interface** — configure the settings/menu wallpaper, title bar style and position, window buttons, interface animations, and menu appearance.
- 🎛️ **System tray controls** — manage playback, display modes, synchronization, quick customization, settings, and application exit.
- ⌨️ **Global hotkeys** — adjust lyric timing and show or hide the HUD.

---

## 📸 Display Modes

### Player Card

A customizable music player card with album artwork, track information, progress, volume controls, status, and an equalizer visualizer. Choose from multiple card sizes and visual styles, and adjust the card's background, blur, glow, border, and shadow.

### Floating Lyrics

A standalone karaoke overlay that can sit on the desktop wallpaper layer or remain above other windows. Customize line placement, width, size, colors, animations, and effects.

### Card + Floating Lyrics

Combine the player card and floating lyrics for a complete desktop music experience. The card and lyrics can be configured independently, including whether lyrics may appear over the card and clock.

### Live Clock

An optional draggable clock widget that follows the application's theme. Configure the time format, seconds, date, size, opacity, and its own background image, blur, and opacity.

---

## 📋 Requirements

- **Operating system:** Windows 10 or Windows 11.
- **Python:** Python 3.9 or newer when running from source.
- **Internet connection:** Required to retrieve uncached lyrics and search/download Google Fonts.
- **Music app:** A player that exposes playback information through the Windows media session API.
- **Lyrics availability:** A suitable synchronized lyrics entry must be available in LRCLIB for lyrics to display.

---

## 🚀 Getting Started

### Option 1: Run the executable

1. Open the [LyricsScreen Releases](https://github.com/CyberSecPwnerrr/LyricScreen/releases) page.
2. Download the latest Windows executable, if a release is available.
3. Run the downloaded executable and follow any Windows installation prompts.
4. Start playing music in your preferred music app.

The packaged executable includes the dependencies needed to run the application. The installer may request permission to install LyricsScreen under Program Files and create a desktop shortcut.

> **Note:** A downloadable executable must be published in GitHub Releases. If no release is available, use Option 2.

### Option 2: Run from source using Python

#### 1. Install Python

Install Python 3.9 or newer if it is not already installed.

#### 2. Clone the repository

```bash
git clone https://github.com/CyberSecPwnerrr/LyricScreen.git
cd LyricScreen
```

#### 3. Launch LyricsScreen

```bash
python lyrics_hud.py
```

When run from source, LyricsScreen checks for and installs its required Python packages. Optional packages are also attempted for additional features.

#### 4. Start playing music

Play a track in your preferred music app. The **♪ system tray icon** provides access to playback controls, display modes, Quick Customize, and settings.

> **Browser support:** Browser-based music players must expose playback information through the Windows media session API. Hardware media controls are generally available in browsers such as Chrome, Brave, and Edge when media-session integration is enabled.

---

## 🎮 Controls

### Mouse Controls

| Action | Result |
|---|---|
| Click the progress bar | Seek through the track |
| Scroll over the player card | Change volume |
| Right-click the player card | Open the quick menu |
| Click the tray icon | Show or hide the HUD |

The clock can be dragged to reposition it. Use the tray menu's reset-position actions when a widget is difficult to find.

### Global Hotkeys

The default global hotkeys use **Ctrl + Alt + Shift** as the modifier combination.

| Shortcut | Action |
|---|---|
| `Ctrl + Alt + Shift + J` | Adjust lyrics earlier by 100 ms |
| `Ctrl + Alt + Shift + K` | Adjust lyrics later by 100 ms |
| `Ctrl + Alt + Shift + H` | Reset the synchronization offset |
| `Ctrl + Alt + Shift + N` | Snap the current lyric line to the current time |
| `Ctrl + Alt + Shift + V` | Show or hide the HUD |

Hotkeys can be disabled in settings. The tray menu also offers synchronization controls, including snapping the next lyric line to the current time.

### System Tray Menu

The tray menu provides access to:

- Play or pause, next track, and previous track.
- Show or hide the HUD.
- Display mode selection.
- Locking the player card in place.
- Toggling album-art color matching.
- Lyric timing adjustments, reset, and snap-sync.
- Settings and Quick Customize.
- Resetting the card position.
- Quitting the application.

---

## ⚙️ Settings

Open **Settings** from the system tray menu. The available options cover the main player, lyrics, overlay, animations, typography, widgets, and interface.

### Themes and Appearance

Choose a built-in theme or configure a custom look. Adjust accent and secondary colors, text color, adaptive album-art colors, card style, glass effect, blur, background images, border, shadow, glow, and corner radius.

### Lyrics and Typography

Configure lyric size, font weight, spacing, letter case, fill style, custom or gradient colors, outline, shadow, glow color, line spacing, karaoke highlighting, anticipation, fade timing, and placement.

Choose a font installed in the font folder or search Google Fonts and download a font for use in LyricsScreen.

### Animation and Effects

Configure lyric entry, exit, and idle animations. Tune motion, scanlines, glitch intensity, chroma ghosting, flicker, 3D tilt, animation frame rate, and optimization mode.

### Player Card

Configure card size and layout, album artwork, album name, status line, volume, equalizer, synchronization buttons, background image, blur, opacity, glow, and other visual details.

### Floating Overlay

Choose the lyrics layer, target monitor, overlay lyric size, line width, wallpaper dimming, and blend mode. Enable always-on-top behavior or hide the card, clock, and lyrics while a fullscreen application is active.

### Live Clock

Enable or disable the clock and customize 24-hour time, seconds, date, size, opacity, and background image settings. Use **Reset clock position** if you need to return the clock to its default position.

### Interface and Menu

Customize the menu wallpaper, opacity, blur, dimming, interface animations, title bar style, title bar position, alignment, window-button position, height, and visible title-bar elements.

### Welcome Screen and Launch Audio

Enable or disable the startup welcome screen and preview it from settings. Optionally select an audio file to play on launch, set its volume, and test it.

### Profiles and Share Codes

Save and load named settings profiles to switch between configurations. You can also generate a share code for most non-file-based settings and import a code to apply another configuration.

Share codes do not package local files such as custom images, downloaded fonts, or launch audio. Those file paths are intentionally excluded, so the referenced files must be selected separately on another computer.

---

## 🎤 Lyrics and Synchronization

LyricsScreen retrieves synchronized lyrics from [LRCLIB](https://lrclib.net) and caches them locally to reduce repeated network requests.

**Compatibility:** LyricsScreen is designed to work with any music app that provides the required playback information through the Windows media session API. The music app does not need to be specifically integrated into LyricsScreen, but the current track must be detected correctly and suitable synchronized lyrics must be available in LRCLIB.

If lyrics are out of sync, use the global hotkeys or synchronization controls in the tray menu.

- **Fine adjustment:** Shift lyric timing in 100 ms increments.
- **Reset:** Restore the default synchronization offset.
- **Snap sync:** Align the current lyric line with the current playback position.
- **Next-line snap:** Align the next lyric line with the current playback position.
- **Per-track offsets:** Keep individual timing adjustments for specific tracks.
- **Karaoke display:** Adjust anticipation and unsung-text brightness to tune the highlighting effect.

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
| `profiles/` | Saved settings profiles |
| `Font/` | Fonts available to the application, including downloaded fonts where saved |

The application uses the public LRCLIB API to look up lyrics for the current track. An internet connection is needed when lyrics are not available in the local cache. Searching and downloading fonts also requires an internet connection.

Settings share codes contain configuration values rather than local file contents. File paths are excluded from share codes.

---

## 🛠️ Troubleshooting

### No lyrics are showing

- Check whether synchronized lyrics are available on LRCLIB.
- Confirm that the current track's title and artist are detected correctly.
- Check your internet connection if the lyrics have not been cached.

### No media is detected

- Make sure the player appears in the Windows volume flyout media controls.
- Enable browser hardware media controls if using a browser-based player.
- Try playing or pausing the track to refresh the media session.
- Verify that the music app exposes playback information through the Windows media session API.

### Lyrics are out of sync

- Use `Ctrl + Alt + Shift + J` or `Ctrl + Alt + Shift + K` for fine adjustments.
- Use the snap-sync shortcut to align the current lyric line.
- Try snapping the next lyric line from the tray menu.
- Reset the offset if the timing becomes incorrect.

### The player card or clock is off-screen

Open the system tray menu and use **Reset card position** or **Reset clock position** in settings.

### A custom image, font, or sound is missing

Check that the file still exists at the selected path. Share codes do not include local assets; select those files separately after importing a code or moving settings to another computer.

### Google Fonts search or download fails

Check your internet connection and try again. You can also use a font file already available in the application's font folder.

### Dependencies fail to install

Verify that Python 3.9 or newer is installed, then update pip:

```bash
python -m pip install --upgrade pip
```

Retry by launching the application again:

```bash
python lyrics_hud.py
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
- [Google Fonts](https://fonts.google.com/) — searchable font library.

<div align="center">

**LyricsScreen — Your music. Your lyrics. Your desktop.**

Made with 🎵 by [CyberSecPwner](https://github.com/CyberSecPwnerrr)

</div>
