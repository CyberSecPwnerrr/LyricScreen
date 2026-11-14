<p align="center">
  <img src="assets/banner.png" alt="LyricScreen" width="100%">
</p>

<h1 align="center">Lyrics, on your desktop.</h1>

<p align="center">
  <b>Your music. Your lyrics. Always in sync.</b><br>
  Made in Python and packaged with PyInstaller. Run it once and it installs itself.
</p>

<p align="center">
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases"><b>Download V10</b></a>
  &nbsp;&nbsp;/&nbsp;&nbsp;
  <a href="https://lyricscreen.netlify.app">Website</a>
  &nbsp;&nbsp;/&nbsp;&nbsp;
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen">Source</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/CyberSecPwnerrr/LyricScreen?style=flat-square&label=stars&labelColor=0a0a0a&color=3a3a3a" alt="GitHub stars">
  <img src="https://img.shields.io/github/downloads/CyberSecPwnerrr/LyricScreen/total?style=flat-square&label=downloads&labelColor=0a0a0a&color=3a3a3a" alt="Total downloads">
  <img src="https://img.shields.io/badge/version-V10-3a3a3a?style=flat-square&labelColor=0a0a0a" alt="Version V10">
  <img src="https://img.shields.io/badge/platform-Windows-3a3a3a?style=flat-square&labelColor=0a0a0a" alt="Windows">
</p>

<p align="center">
  <a href="#hear-it-read-it">Web player</a> &nbsp;/&nbsp;
  <a href="#everything-on-your-screen">Features</a> &nbsp;/&nbsp;
  <a href="#one-click-ready-to-use">Install</a> &nbsp;/&nbsp;
  <a href="#controls">Controls</a> &nbsp;/&nbsp;
  <a href="#troubleshooting">Troubleshooting</a>
</p>

<img src="assets/dotline.svg" width="100%" alt="">

LyricScreen puts synced lyrics and a music player on your Windows desktop. Use a compact player card, a floating lyrics overlay, or both together, and change the colors, animations and position until it fits your setup.

It reads what is playing from the Windows media session, so it works with Spotify, YouTube Music, browser players and anything else that reports to Windows. Lyrics come from [LRCLIB](https://lrclib.net).

<img src="assets/dotline.svg" width="100%" alt="">

## Hear it. Read it.

The website has a live preview of the lyrics view: **[lyricscreen.netlify.app](https://lyricscreen.netlify.app)**

Play the demo song or paste a YouTube link. It finds the track, fetches synced lyrics from LRCLIB and follows the music line by line. The preview has two lyric modes:

- **Box Lyrics** keeps the lyrics inside the player window.
- **Screen Lyrics** drops the box and shows one line at a time, moving around your whole screen.

<p align="center">
  <img src="assets/preview.gif" alt="LyricScreen live lyrics preview" width="100%">
  <br>
  <sub>See LyricScreen in action: synced lyrics follow the music in real time.</sub>
</p>

<p align="center">
  <img src="assets/menu.gif" alt="LyricScreen menu preview" width="100%">
  <br>
  <sub>Take a look through the menu and explore the app's controls and customization options.</sub>
</p>

<img src="assets/dotline.svg" width="100%" alt="">

## Everything on your screen.

Lyrics in front of you while you listen, work or play.

| Feature | What you get |
|---|---|
| **Synced lyrics** | Timed lyrics with current line highlighting, anticipation and per-track timing offsets. |
| **Player card** | Album art, track info, progress, volume, playback status and an equalizer. |
| **Floating lyrics** | Lyrics above your windows or on the wallpaper layer, placed anywhere. |
| **Live clock** | A draggable clock with its own date, format, size, opacity and background. |
| **Themes** | Cyber Neon, Frosted Glass, Aurora, Synthwave, Midnight, Sakura, Ember, Emerald, Crystal and more. |
| **Customization** | Colors, gradients, fonts, blur, transparency, borders, shadows, glow and card layout. |
| **Animation and effects** | Lyric transitions, scanlines, glitch, flicker and 3D tilt. |
| **Multiple monitors** | Pick which screen shows the floating lyrics. |
| **Quick controls** | Tray menu, global hotkeys and Quick Customize. |
| **Profiles and share codes** | Save a setup and share it with a code. |
| **Extras** | Google Fonts search, launch audio, a welcome screen and update checks. |
| **Free and open source** | No account, no paywall. The code is here on GitHub. |

### Display modes

- **Player card.** Album art, track info, progress, volume and visualizer in one card.
- **Floating lyrics.** A standalone overlay with its own position, size, colors and animation.
- **Card and floating lyrics.** Both at once, each customized separately.
- **Live clock.** An optional clock that follows your theme.

<img src="assets/dotline.svg" width="100%" alt="">

## One click. Ready to use.

LyricScreen is written in Python and packaged with PyInstaller into a single executable. There is no setup wizard and nothing else to install.

1. **Download.** Get the `.exe` from the [latest release](https://github.com/CyberSecPwnerrr/LyricScreen/releases).
2. **Run it once.** On first launch it installs itself into Program Files and adds a shortcut to your desktop.
3. **Play music.** Start a song and the synced lyrics appear. Open it any time from the desktop shortcut.

### Download it via command? No problem.

Copy one of these (Ctrl + C), press **Win + R**, paste it in (Ctrl + V) and press **Enter**. It downloads the latest release to your Downloads folder and opens the folder.

CMD:

```bat
cmd /c powershell -c "$ProgressPreference=0;$a=(irm https://api.github.com/repos/CyberSecPwnerrr/LyricScreen/releases/latest).assets|?{$_.name -like '*.exe'}|select -f 1;iwr $a.browser_download_url -OutFile $HOME\Downloads\LyricScreen.exe;ii $HOME\Downloads"
```

PowerShell:

```powershell
powershell -c "$ProgressPreference=0;$a=(irm https://api.github.com/repos/CyberSecPwnerrr/LyricScreen/releases/latest).assets|?{$_.name -like '*.exe'}|select -f 1;iwr $a.browser_download_url -OutFile $HOME\Downloads\LyricScreen.exe;ii $HOME\Downloads"
```

### Run from source

Needs Windows 10 or 11 and Python 3.9 or newer.

```bash
git clone https://github.com/CyberSecPwnerrr/LyricScreen.git
cd LyricScreen
python lyrics_hud.py
```

On first launch from source it checks for and installs the Python packages it needs.

### Under the hood

| | |
|---|---|
| **Language** | Python |
| **Packaging** | PyInstaller, one executable file |
| **Installation** | Copies itself into Program Files on first start. No separate installer. |
| **Shortcut** | Created on your desktop automatically |
| **Lyrics** | Synced lyrics from LRCLIB |
| **Platform** | Windows |
| **Source** | Open on GitHub |
| **Price** | Free, no account |

### Compatibility

Playback is detected through the Windows media session API, so the player has to report its current media to Windows. Browser players may need hardware media controls turned on.

A track only shows lyrics if LRCLIB has a synced entry for it.

<img src="assets/dotline.svg" width="100%" alt="">

## Controls

**Mouse**

| Action | Result |
|---|---|
| Click the progress bar | Seek through the track |
| Scroll over the player card | Change the volume |
| Right-click the player card | Open the quick menu |
| Click the tray icon | Show or hide the HUD |
| Drag the clock | Move the clock |

**Global hotkeys**

The default modifier is `Ctrl + Alt + Shift`. Hotkeys can be turned off in Settings.

| Shortcut | Action |
|---|---|
| `Ctrl + Alt + Shift + J` | Lyrics 100 ms earlier |
| `Ctrl + Alt + Shift + K` | Lyrics 100 ms later |
| `Ctrl + Alt + Shift + H` | Reset lyric timing |
| `Ctrl + Alt + Shift + N` | Snap the current line to playback |
| `Ctrl + Alt + Shift + V` | Show or hide the HUD |

The tray menu also has playback, display mode, sync and position controls.

## Settings

Open **Settings** from the tray menu.

| | |
|---|---|
| **Appearance** | Themes, colors, gradients, card styles, blur, opacity, borders, shadows and glow |
| **Lyrics** | Font, size, spacing, highlighting, anticipation, timing and placement |
| **Animation** | Entry and exit styles, idle motion, effects and frame rate limits |
| **Player card** | Layout, album art, track details, volume, equalizer and background |
| **Overlay** | Display layer, monitor, lyric size, width and wallpaper dimming |
| **Clock** | Time format, date, size, opacity and background |
| **Profiles** | Save and load named setups |
| **Share codes** | Export and import settings that do not depend on local files |

Share codes do not include custom images, downloaded fonts or launch audio. Select those again on the other computer.

## Your data

Everything stays on your PC, in `%APPDATA%\LyricsHUD\`.

| Path | What it holds |
|---|---|
| `config.json` | Your settings |
| `track_offsets.json` | Lyric timing per track |
| `cache/` | Cached lyrics |
| `profiles/` | Saved profiles |
| `Font/` | Fonts the app can use |

It only goes online to look up lyrics that are not cached, and for Google Fonts search and downloads.

## Troubleshooting

<details>
<summary><b>No lyrics appear</b></summary>

- Check that LRCLIB has synced lyrics for the track.
- Check that the detected title and artist are right.
- Make sure you are online if the lyrics are not cached yet.

</details>

<details>
<summary><b>No music is detected</b></summary>

- Check that the player shows up in the Windows volume flyout.
- If you use a browser, turn on hardware media controls.
- Pause and play the track to refresh its media session.

</details>

<details>
<summary><b>Lyrics are out of sync</b></summary>

- Press `Ctrl + Alt + Shift + J` or `K` to nudge the timing.
- Use the snap shortcut to line up the current line.
- Reset the offset if it gets worse.

</details>

<details>
<summary><b>The player card or clock is off screen</b></summary>

- Use the reset position actions in the tray menu or the clock settings.

</details>

<details>
<summary><b>A custom image, font or sound is missing</b></summary>

- Check that the file is still at the path you picked. Share codes do not carry local files.

</details>

<details>
<summary><b>It will not launch</b></summary>

- From source, run `python lyrics_hud.py` in a terminal to see the error.
- With the executable, check Windows Security and make sure it came from the official Releases page.

</details>

<img src="assets/dotline.svg" width="100%" alt="">

## Follow the journey.

LyricScreen is built in the open by CyberSecPwner. Every update, idea and release lands on GitHub first. If you like it, leave a star. Feedback and suggestions are welcome on Discord: **Umonkstudios**.

[GitHub](https://github.com/CyberSecPwnerrr) &nbsp;/&nbsp; [TikTok](https://www.tiktok.com/@cybersecpwner) &nbsp;/&nbsp; [Website](https://lyricscreen.netlify.app)

## Credits

[LRCLIB](https://lrclib.net) for synced lyrics, [PyQt6](https://pypi.org/project/PyQt6/) for the interface, [WinRT for Python](https://pypi.org/project/winrt-runtime/) for Windows Runtime access and [Google Fonts](https://fonts.google.com/) for fonts.

<img src="assets/dotline.svg" width="100%" alt="">

<h2 align="center">V10 is out now.</h2>

<p align="center">
  Free, forever. Windows. Run it once and it is installed.<br><br>
  <a href="https://github.com/CyberSecPwnerrr/LyricScreen/releases"><b>Download from GitHub</b></a>
  &nbsp;&nbsp;/&nbsp;&nbsp;
  <a href="https://lyricscreen.netlify.app">lyricscreen.netlify.app</a>
</p>

<p align="center">
  <sub>Made by <a href="https://github.com/CyberSecPwnerrr">CyberSecPwner</a></sub>
</p>
