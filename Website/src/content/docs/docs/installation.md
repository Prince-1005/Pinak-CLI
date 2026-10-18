---
title: Installation
description: Install Pinak with pipx, an isolated virtual environment, or source.
---

Use the site's **Install** page for the complete platform-specific walkthrough. The essential steps are below.

## Prerequisites

- Python 3.10 or newer for Pinak. The current pipx release requires Python 3.11 or newer; Python 3.10 users can use a virtual environment or a compatible distribution-packaged pipx.
- pipx, or a Python virtual environment.
- Network access to the source for downloads.
- FFmpeg for merging, conversion, audio extraction, and playback.

## Windows

Install Python with its launcher, then run in PowerShell:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Reopen PowerShell, then:

```sh
pipx install pinak-cli
```

## macOS

With Homebrew installed:

```sh
brew install python pipx
pipx ensurepath
```

Reopen Terminal, then `pipx install pinak-cli`.

## Debian / Ubuntu

```sh
sudo apt update
sudo apt install python3 python3-venv pipx
pipx ensurepath
```

Reopen your terminal, then `pipx install pinak-cli`. Other distributions should use their corresponding packages.

## Check installation

```sh
pinak --version
pinak --help
pinak --doctor
```

## Virtual environment alternative

On Windows, create an environment with `py -m venv .venv` and activate it using `.\.venv\Scripts\Activate.ps1`.

On macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

Inside the activated environment:

```sh
python -m pip install pinak-cli
```

## From source

```sh
git clone https://github.com/Prince-1005/Pinak-CLI.git
cd Pinak-CLI
```

Create and activate an environment, then `python -m pip install ./cli`.

## FFmpeg and optional playback setup

Pinak includes a static FFmpeg provisioning utility. Run `pinak --install-ffmpeg` if needed, or install FFmpeg using your OS tools. Use `pinak --doctor` to inspect your environment.

On Debian/Ubuntu, optional desktop playback prerequisites are:

```sh
sudo apt install ffmpeg libportaudio2 python3-tk
```

Tkinter must match the Python interpreter used for Pinak. A graphical desktop and an audio output device are needed for their respective playback features. For an alternative native-window backend in a pipx installation:

```sh
pipx inject pinak-cli opencv-python
```

Do not choose `opencv-python-headless` for desktop windows. See [playback](../playback/) for controls and limitations.
