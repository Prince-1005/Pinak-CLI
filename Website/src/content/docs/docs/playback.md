---
title: Playback & subtitles
description: Open local media, navigate the player, and use available subtitle tracks.
---

## Open a collection

```sh
pinak media "<local-file-or-directory>"
```

Or use `/media`, `/play`, or `/view` inside the interactive shell. With no path, the browser lets you navigate local files. The player accepts local files/directories; it does not turn arbitrary remote URLs into a streaming player.

Interactive playback needs a terminal. Native windows require a graphical desktop; audio needs a functioning output device.

## Controls

- **Space:** pause/resume.
- **Left/right:** seek audio/video.
- **Up/down:** change audio volume.
- **Ctrl+M:** mute.
- **n / p:** next/previous track.
- **r:** repeat mode.
- **m:** terminal renderer.
- **w:** toggle an available native window.
- **c:** cycle available video subtitles.
- **Esc / x:** close media.

In picture viewing, arrows pan, **+ / −** zoom, and **r / R** rotate. Picture controls differ from audio/video controls.

## Rendering

Available presentation depends on your terminal capabilities and environment. Native playback and terminal rendering have different detail budgets. The screenshots on this website demonstrate particular local setups, not identical output guaranteed for every terminal.

## Subtitles

Pinak can discover supported sibling subtitle files and extract embedded subtitle tracks in the background. Availability depends on the media. There is no automatic speech-to-text generation.

In the interactive shell, `/subs` toggles optional subtitle extraction and embedding for future supported downloads. This setting does not create captions when no captions are available from the source.

## Playback prerequisites

On Debian/Ubuntu:

```sh
sudo apt install ffmpeg libportaudio2 python3-tk
```

For a pipx installation using OpenCV as an alternative native backend:

```sh
pipx inject pinak-cli opencv-python
```

Tkinter must match the Python interpreter. OpenCV headless packages do not provide windows. Containers are configured for downloading, not automatic desktop/audio forwarding.

Run `pinak --doctor` to begin troubleshooting. Low resources or critical device health can require confirmation before playback.
