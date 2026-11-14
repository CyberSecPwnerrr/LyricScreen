<div align="center">

<img src="assets/banner.png" alt="LyricsScreen banner" width="100%">

<br>

<a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases"><img src="https://img.shields.io/badge/●%20V10%20out%20now-0a0a0a?style=for-the-badge&labelColor=0a0a0a" alt="V10 out now"></a>

# Lyrics, on your desktop.

**Your music. Your lyrics. Always in sync.**

Made in Python and packaged with PyInstaller. Run it once and it installs itself.

<p>
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases"><img src="https://img.shields.io/badge/Download-V10-1c1c1c?style=for-the-badge&logo=github&logoColor=white" alt="Download V10"></a>
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen"><img src="https://img.shields.io/badge/Star%20on-GitHub-1c1c1c?style=for-the-badge&logo=github&logoColor=white" alt="Star on GitHub"></a>
  <a href="https://lyricscreen.netlify.app"><img src="https://img.shields.io/badge/Website-lyricscreen.netlify.app-1c1c1c?style=for-the-badge&logo=netlify&logoColor=white" alt="Website"></a>
</p>

<p>
  <img src="https://img.shields.io/github/stars/CyberSecPwnerrr/LyricScreen?style=for-the-badge&logo=github&label=GitHub%20stars&labelColor=0a0a0a&color=3a3a3a" alt="GitHub stars">
  <img src="https://img.shields.io/github/downloads/CyberSecPwnerrr/LyricScreen/total?style=for-the-badge&logo=github&label=Total%20downloads&labelColor=0a0a0a&color=3a3a3a" alt="Total downloads">
  <img src="https://img.shields.io/badge/Latest%20version-V10-3a3a3a?style=for-the-badge&labelColor=0a0a0a" alt="Latest version V10">
</p>

<p>
  <a href="#everything-on-your-screen">Features</a> ·
  <a href="#hear-it-read-it">Web player</a> ·
  <a href="#one-click-ready-to-use">Install</a> ·
  <a href="#controls">Controls</a> ·
  <a href="#troubleshooting">Troubleshooting</a>
</p>

</div>

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

## What is LyricsScreen?

LyricsScreen shows live, time-synced lyrics and a customizable music HUD on your Windows desktop. Use a compact player card, a floating karaoke overlay, or both together. Colors, animations and position are yours to change.

It reads playback information from the Windows media session API, so it works with compatible apps such as Spotify, YouTube Music and browser-based players. Synchronized lyrics come from [LRCLIB](https://lrclib.net).

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

## Hear it. Read it.

Try the preview on the website: **[lyricscreen.netlify.app](https://lyricscreen.netlify.app)**

Play a song from the songs folder, or paste a YouTube link. The player finds the track, fetches synced lyrics from LRCLIB and follows the music line by line.

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

## Everything on your screen.

Built for people who want lyrics in front of them while they listen, work or play.

| | |
|---|---|
| **Synchronized lyrics** | Timed lyrics with current-line highlighting, anticipation and per-track timing offsets. |
| **Player card** | Album art, track details, progress, volume, playback status and an equalizer. |
| **Floating lyrics** | Place lyrics above your desktop or on the wallpaper layer. |
| **Live clock** | A draggable clock with configurable date, time format, size, opacity and background. |
| **Themes** | Cyber Neon, Frosted Glass, Aurora, Synthwave, Midnight, Sakura, Ember, Emerald, Crystal and more. |
| **Customization** | Colors, gradients, fonts, blur, transparency, borders, shadows, glow and card layout. |
| **Animations and effects** | Lyric transitions, scanlines, glitch effects, flicker and 3D tilt. |
| **Multiple monitors** | Choose the display for the floating lyrics. |
| **Quick controls** | System tray menu, global hotkeys and Quick Customize. |
| **Profiles and share codes** | Save settings or share most non-file-based customization. |
| **Optional extras** | Google Fonts search, launch audio, welcome screen and automatic update checks. |
| **Free and open source** | No account, no paywall. The code is on GitHub. |

### Display modes

**Player card** — A desktop music card showing album artwork, track information, playback progress, volume and visualizer.

**Floating lyrics** — A standalone karaoke-style overlay with adjustable position, size, colors and animation.

**Card + floating lyrics** — Use the player card and lyrics overlay together. Each can be customized independently.

**Live clock** — An optional draggable clock that follows the application's theme.

> Add screenshots to the repository and link them here when ready. For example: `![Player card](assets/player-card.png)`

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

## One click. Ready to use.

LyricsScreen is written in Python and packaged with PyInstaller into a single executable. There is no setup wizard and nothing else to install.

**1. Download** — Get the .exe from the latest release on GitHub.

**2. Run it once** — On first launch it installs itself into Program Files and puts a shortcut on your desktop.

**3. Play music** — Start a song and the synced lyrics appear. Open it any time from the desktop shortcut.

### Download it via command? No problem.

Copy one of these (Ctrl + C), press **Win + R**, paste it in (Ctrl + V) and press **Enter**. It fetches the latest release and saves it to your Downloads folder.

**CMD**

```bat
cmd /c powershell -c "$ProgressPreference=0;$a=(irm https://api.github.com/repos/CyberSecPwnerrr/LyricScreen/releases/latest).assets|?{$_.name -like '*.exe'}|select -f 1;iwr $a.browser_download_url -OutFile $HOME\Downloads\LyricScreen.exe;ii $HOME\Downloads"
```

**PowerShell**

```powershell
powershell -c "$ProgressPreference=0;$a=(irm https://api.github.com/repos/CyberSecPwnerrr/LyricScreen/releases/latest).assets|?{$_.name -like '*.exe'}|select -f 1;iwr $a.browser_download_url -OutFile $HOME\Downloads\LyricScreen.exe;ii $HOME\Downloads"
```

### Run from source

**Requirements:** Windows 10 or 11 and Python 3.9 or newer.

```bash
git clone https://github.com/CyberSecPwnerrr/LyricScreen.git
cd LyricScreen
python lyrics_hud.py
```

When launched from source, LyricsScreen checks for and installs its required Python packages.

### Under the hood

| | |
|---|---|
| **Language** | Python. |
| **Packaging** | PyInstaller, built into one executable file. |
| **Installation** | The program copies itself into Program Files on first start. No separate installer. |
| **Shortcut** | A desktop shortcut is created automatically, so it is ready right away. |
| **Lyrics** | Synced lyrics from LRCLIB. |
| **Platform** | Windows. |
| **Source** | Open on GitHub. You can also run it from source. |
| **Price** | Free, with no account. |

### Compatibility

LyricsScreen uses the Windows media session API to detect playback. The player must expose its current media session to Windows. Browser-based players may require hardware media controls to be enabled.

Lyrics are provided by LRCLIB. A track needs a matching synchronized-lyrics entry for lyrics to appear.

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

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

Hotkeys can be disabled in Settings. The tray menu also includes playback, display-mode, synchronization and position controls.

## Settings

Open **Settings** from the system tray menu.

| | |
|---|---|
| **Appearance** | Themes, colors, gradients, card styles, blur, opacity, borders, shadows and glow. |
| **Lyrics** | Font, size, spacing, highlighting, anticipation, timing and placement. |
| **Animation** | Entry and exit styles, idle motion, visual effects and frame-rate limits. |
| **Player card** | Layout, album art, track details, volume, equalizer and background. |
| **Overlay** | Display layer, monitor selection, lyric size, width and wallpaper dimming. |
| **Clock** | Time format, date, size, opacity and background. |
| **Profiles** | Save and load named settings profiles. |
| **Share codes** | Export and import most settings that do not depend on local files. |

Share codes do not include custom images, downloaded fonts or launch-audio files. Those files must be selected separately on another computer.

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

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

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

**A custom image, font or sound is missing**
- Check that the file still exists at its selected path. Share codes do not package local files.

**The application does not launch**
- If running from source, launch it in a terminal with `python lyrics_hud.py` to see error messages.
- If using the executable, check Windows Security and make sure it came from the official Releases page.

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

## Follow the journey.

LyricsScreen is built in the open by CyberSecPwner. Every update, idea and release lands on GitHub first. If you like it, leave a star on the repo. Feedback and suggestions are welcome, send them on Discord: **Umonkstudios**.

<p>
  <a href="https://github.com/CyberSecPwnerrr"><img src="https://img.shields.io/badge/Follow%20on-GitHub-1c1c1c?style=for-the-badge&logo=github&logoColor=white" alt="Follow on GitHub"></a>
  <a href="https://www.tiktok.com/@cybersecpwner"><img src="https://img.shields.io/badge/Follow%20on-TikTok-1c1c1c?style=for-the-badge&logo=tiktok&logoColor=white" alt="Follow on TikTok"></a>
  <a href="https://lyricscreen.netlify.app"><img src="https://img.shields.io/badge/Visit-the%20website-1c1c1c?style=for-the-badge&logo=netlify&logoColor=white" alt="Visit the website"></a>
</p>

## Credits

- [LRCLIB](https://lrclib.net) — synchronized lyrics.
- [PyQt6](https://pypi.org/project/PyQt6/) — application interface.
- [WinRT for Python](https://pypi.org/project/winrt-runtime/) — Windows Runtime integration.
- [Google Fonts](https://fonts.google.com/) — font library.
- [CyberSecPwner](https://github.com/CyberSecPwnerrr) — creator.

<p align="center">· · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·</p>

<div align="center">

## V10 is out now.

Free, forever. Windows. Run it once and it is installed.

<a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases"><img src="https://img.shields.io/badge/Download%20from-GitHub-1c1c1c?style=for-the-badge&logo=github&logoColor=white" alt="Download from GitHub"></a>
<a href="https://lyricscreen.netlify.app"><img src="https://img.shields.io/badge/Website-lyricscreen.netlify.app-1c1c1c?style=for-the-badge&logo=netlify&logoColor=white" alt="Website"></a>

**LyricsScreen** · Your music, your lyrics, your desktop.

Made by [CyberSecPwner](https://github.com/CyberSecPwnerrr)

</div>
