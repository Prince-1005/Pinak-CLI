# Pinak CLI 2.3.0

See [CLI_README.md](CLI_README.md) for usage and
[OPERATIONS.md](OPERATIONS.md) for current configuration, playback, recovery,
dependency and release behavior.

See [CHANGELOG.md](CHANGELOG.md) for release notes. Releases are created manually;
automatic release creation is disabled.

Requires Python 3.10 or newer. Install with `python -m pip install .`.

The optional local MCP adapter is implemented in this source checkout. Install
with `python -m pip install -e ".[mcp]"`, then run `pinak-mcp doctor` and
`pinak-mcp configure` for client-neutral stdio launch fields. See
[`MCP(Local)/USAGE.md`](<../MCP(Local)/USAGE.md>) for connection, policy and recovery instructions.
Published packages may not include these unreleased changes yet.

For a remote instance you operate yourself, use [Pinak-MCP Cloud](<../MCP(cloud)/README.md>) and its [hosting walkthrough](<../MCP(cloud)/HOSTING_STEPS.md>). Pinak does not provide a shared cloud service.
