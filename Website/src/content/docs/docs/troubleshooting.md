---
title: Diagnostics & troubleshooting
description: Resolve installation, extraction, FFmpeg, and playback problems.
---

## Begin with facts

```sh
pinak --version
pinak --doctor
pinak --help
```

For a failing URL, add `--verbose` and optionally `--log-file <path>`. Review logs before sharing them; remove private URLs, local identifiers, or credentials.

## “pinak” is not found

After pipx installation, run `pipx ensurepath`, then reopen your terminal. If using a virtual environment, activate it first. Check `pipx list` or `python -m pip show pinak-cli` in the environment you actually use.

## Python or pip installation is blocked

Pinak requires Python 3.11+ so patched Pillow and FileLock releases can be installed. If you have Python 3.10, install a supported Python interpreter and recreate the Pinak environment. On Debian/Ubuntu, install pipx with `apt` rather than overriding system Python protections. Match your shell/interpreter to the installation instructions.

## FFmpeg is missing

```sh
pinak --install-ffmpeg
pinak --doctor
```

Alternatively install FFmpeg with OS tooling and ensure it is discoverable. Configuration supports explicit FFmpeg/FFprobe paths. Audio extraction and stream merging depend on working processing tools.

## A source stopped working

Update yt-dlp in the Pinak environment, verify network connectivity, and confirm the URL is accessible. Source changes, removals, private access, and format availability are outside Pinak’s control. An extraction failure does not imply that the downloader can bypass source restrictions.

## A download was interrupted

Re-run the same command to attempt continuation from retained partial files. Check the result and final output, not just the presence of a partial file. Use `--force` only if you intend to bypass duplicate policy.

## There is no audio

Check system output/mute settings and the selected working device. On Linux install PortAudio as appropriate. Being able to download media does not prove that desktop audio drivers are configured.

## A native window does not open

Use a graphical desktop and matching Tkinter, or optional GUI-enabled OpenCV in the same Python environment. A headless terminal or container may support downloading but not a native window.

## The terminal looks wrong after closing

Inside the REPL, try `/reset`. If needed, close and reopen your terminal. Try a larger terminal window for very small layouts.

## Report a reproducible issue

Include OS, terminal, installed Pinak/Python versions, the command used, and a redacted error. Explain expected versus actual behavior. Do not include session cookies, private credentials, or media you cannot share.
