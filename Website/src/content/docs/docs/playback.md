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

An open GPU/native window stays open when playback advances to another song or
video, including shuffle and repeat. Its media and title update in place while
its size and fullscreen state remain. Press **w** to close the window explicitly,
or close playback to release it.

## Controls

In the file browser, the selected filename wraps in both panels. Use **left/right**
to page through especially long names; choosing another item returns to its first
name page. The Media Inspector shows audio/video **Length** as `M:SS` or
`H:MM:SS`. It loads in the background without blocking navigation. When duration
cannot be read, the inspector displays **Unavailable**.

During playback:

- **Space:** pause/resume.
- **Left/right:** seek audio/video.
- **Up/down:** change audio volume.
- **Ctrl+M:** mute.
- **n / p:** next/previous track.
- **r:** repeat mode.
- **s:** shuffle on/off for songs and videos; the header shows `Shuf: ON/OFF`.
- **m:** terminal renderer.
- **w:** toggle an available native window.
- **c:** cycle available video subtitles.
- **Esc / x:** close media.

In picture viewing, arrows pan, **+ / −** zoom, and **r / R** rotate. Picture controls differ from audio/video controls.

## Shuffle and repeat

Press **s** to toggle shuffle without changing the playing track. Press **r** to
cycle repeat through **OFF → ALL → SOLO → OFF**. ALL is the repeat-on mode.

- **Shuffle + ALL:** each next track is randomly chosen from the full playlist.
  A track can be selected again, including the current track.
- **Shuffle + OFF:** each next track is randomly chosen from tracks not yet
  played in this player session. After all tracks have played, playback pauses
  on the last track. Music does not wrap around in this mode.
- **Shuffle + SOLO:** completion restarts the current track repeatedly.

**n / p** still let you navigate manually; **p** follows playback history while
shuffle is on. Manual navigation can change the current track in SOLO. Switching
shuffle off returns to normal playlist order, keeping the current track. Toggling
shuffle or repeat does not erase the session's played-track history. Reopen the
collection to start a fresh session.

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
