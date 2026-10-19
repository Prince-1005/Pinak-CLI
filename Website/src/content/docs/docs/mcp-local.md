---
title: Set up Local MCP
description: Install the Local MCP bundle, check FFmpeg, and register a stdio process in your AI application.
---

Local MCP runs on your own device. You need Python 3.10+ and an AI application that can launch **stdio MCP** processes. No listening port, cloud account, domain, or Pinak account is required.

## 1. Download and verify

Follow the [installer selection guide](../mcp/#obtain-an-installer) and download **pinak-mcp-install**. Extract it into a permanent folder. Use the wheel filename in that bundle's `INSTALL.md`; do not move the environment after registering it with your client.

On Linux, verify the bundle with `sha256sum -c SHA256SUMS`. On macOS, use `shasum -a 256 -c SHA256SUMS`. In PowerShell, compare `Get-FileHash -Algorithm SHA256 WHEEL_FILENAME` with the wheel's entry in `SHA256SUMS`. Replace `WHEEL_FILENAME` with the actual filename.

## 2. Install in its own environment

Run inside the extracted installer folder. Replace `WHEEL_FILENAME` below with the included `.whl` filename.

**Windows / PowerShell:**

```powershell
python -m venv .venv-mcp
.venv-mcp/Scripts/python.exe -m pip install --upgrade pip
.venv-mcp/Scripts/python.exe -m pip install "./WHEEL_FILENAME[mcp]"
.venv-mcp/Scripts/python.exe -m pinak.mcp_server doctor --json
.venv-mcp/Scripts/python.exe -m pinak.mcp_server configure
```

**macOS / Linux:**

```sh
python3 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install --upgrade pip
.venv-mcp/bin/python -m pip install "./WHEEL_FILENAME[mcp]"
.venv-mcp/bin/python -m pinak.mcp_server doctor --json
.venv-mcp/bin/python -m pinak.mcp_server configure
```

Install FFmpeg/FFprobe explicitly for conversion, merging, and metadata inspection. MCP diagnostics do not download these binaries automatically. Review doctor results before trying a download. You do not need Git or Node.js for bundle installation.

## 3. Register with your AI application

`configure` prints the launch settings for the installed environment:

- Transport: `stdio`.
- Command: the **absolute path** to that environment's Python executable.
- Arguments: `-m`, `pinak.mcp_server`, `serve`, `--transport`, `stdio`, as separate values.
- Environment: `PINAK_MCP_CONFIG`, using the printed absolute policy filename.

Enter these in your application's local MCP settings, then reload/reconnect. Configuration formats vary between clients. No shell activation script is required. A remote-URL-only client cannot launch this edition.

Discover fourteen tools, then ask the AI to queue a URL, start the queue, and inspect its status. Adding alone does not start downloading. The default download location is your user's `Downloads/Pinak` folder. CLI and Local MCP share the existing per-user queue/history.

## 4. Configure storage and update safely

The policy file controls approved output and read roots. Use absolute paths from the supplied examples. This is application-level path checking, not an OS sandbox.

For updates, stop active work, close the AI host, and run `-m pinak.mcp_server prepare-update` using the existing environment's Python. Install the new bundled wheel through the same Python with `--force-reinstall` and the `[mcp]` extra; follow its `INSTALL.md` and maintenance guide.

See [complete Local usage](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28Local%29/USAGE.md), [policy examples](https://github.com/Prince-1005/Pinak-CLI/tree/main/MCP%28Local%29/examples), and [maintenance](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28Local%29/MAINTENANCE.md). For remote clients, [host your own Cloud MCP](../mcp-cloud/).
