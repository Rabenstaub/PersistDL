<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="PersistDL logo">
</p>

# PersistDL

A Windows download manager that resumes broken downloads exactly where they
left off — whether the interruption was seconds ago or days ago.

Built to reliably pull large files (AI model checkpoints, LoRAs, etc. from
sites like Civitai) that keep dropping mid-download on a flaky connection.

## Features

- **Byte-exact resume** via HTTP range requests — nothing is re-downloaded,
  nothing is missing. Works even after a full PC reboot.
- **Automatic reconnect** on network errors (interval configurable, unlimited
  retries).
- **Change detection**: if the file on the server changed (ETag/Last-Modified),
  the download restarts safely instead of producing a corrupted file.
- **Queue mode**: downloads run one after another; add more links anytime,
  even while something is already downloading.
- **Per-download destination folder**, with a dropdown of your last 15 used
  folders.
- **Large-file support**: correct size/percentage/ETA for files well over 2 GB
  (e.g. `.safetensors` model checkpoints).
- **Persistent history**: finished downloads stay in the list across restarts
  until you remove them.
- **One-click folder access**: a button next to every row jumps straight to
  the file in Explorer (or the `.part` file, if it's still downloading).
- **"Clear list"** removes everything from the list at once; the right-click
  menu also offers removing just the finished entries.
- **Optional forced shutdown** once every queued download finishes, with a
  60-second on-screen + audible countdown and a one-click cancel.
- **Finish sound**, custom MP3/WAV supported.
- **Browser interception** ("PersistDL Catcher", a Chrome/Edge/Brave
  extension): catches the browser's download click and hands it to PersistDL
  instead of downloading it in the browser. If PersistDL isn't running, the
  browser just downloads normally — nothing is ever lost.
- **Civitai API token** field: automatically appended to civitai.com download
  links, so gated/login-required models work too.

## Requirements

- Windows
- Python 3.9+ (tested on 3.11)
- `PyQt6` and `requests` — installed automatically on first run

## Quick start

1. Double-click `Start.bat`.
   (On the very first run it installs `PyQt6` and `requests` for you —
   output goes to `install_log.txt`.)
2. Paste a download link (or click "Paste" to grab it from the clipboard),
   pick a folder, and click "Start Download".

Having trouble? `Debug.bat` runs the tool with a visible console so you can
see the actual error; every crash is also logged to `persistdl_error.log`.

## Browser extension (optional)

The `browser-extension/` folder contains "PersistDL Catcher" for
Chromium-based browsers (Chrome, Edge, Brave). It lets you click a normal
"Download" button on a site like Civitai and have the file land in PersistDL
instead of your browser's download manager.

Setup steps: see [`browser-extension/INSTALLATION.txt`](browser-extension/INSTALLATION.txt).

## Language

The UI ships in English, German, Spanish, French, Japanese, Korean,
Portuguese (Brazil), and Chinese (Simplified). **English is the default**;
switch language via the "Language" dropdown in the app — it takes effect
after restarting PersistDL. Want another language? Copy `lang/en.json` to
e.g. `lang/it.json`, translate the values (leave the keys as they are), and
pick it from the dropdown — no code changes needed. The dropdown lists
whatever `.json` files it finds in `lang/`.

## Configuration

Settings (target folder history, retry behavior, Civitai token, window
layout, ...) are stored in:

```
%USERPROFILE%\.persistdl_settings.json
```

## License

PersistDL is **free to download and use**, but the source stays under the
author's copyright — see [`LICENSE.md`](LICENSE.md) for what is and isn't
allowed (in short: free personal use and private modifications are fine;
reselling, redistributing, or claiming authorship of it or a modified version
is not, without permission).

## Credits

Made by [Rabenstaub](https://github.com/Rabenstaub).
