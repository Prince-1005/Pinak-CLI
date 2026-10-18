---
title: Updating & contributing
description: Maintain an installation and contribute to Pinak or its website.
---

## Update a pipx installation

```sh
pipx upgrade pinak-cli
```

Inside the interactive shell, `/update` updates yt-dlp and Pinak. For yt-dlp alone in a pipx environment:

```sh
pipx runpip pinak-cli install --upgrade yt-dlp
```

For a virtual environment, activate it and run `python -m pip install --upgrade pinak-cli`. Verify using `pinak --version`.

## Python development

Clone the repository and create/activate a virtual environment. From its root:

```sh
python -m pip install --require-hashes -r cli/requirements-lock.txt
python -m pip install --no-deps -e ./cli
pre-commit install --config cli/.pre-commit-config.yaml
```

Run the package checks from `cli` using the maintained project configuration. Releases are manual and verified; a push does not automatically publish a new PyPI version.

## Website development

The static website lives separately under `Website`. Node.js is a website development/build dependency, not a requirement for installing the Python package.

```sh
cd Website
npm ci
npm run dev
```

Media preparation uses FFmpeg/FFprobe. See `Website/README.md` and its planning/media-maintenance guides for asset preparation and deployment configuration.

## Contributions that help

Useful changes include reproducible bug fixes, tested platform setup instructions, original product demonstrations, clearer troubleshooting, and accessible documentation. Keep feature claims tied to implemented behavior and distinguish sample media from real product captures.
