# Configuration examples

These templates use placeholders, not real installation paths. Install the source
MCP extra first and use `pinak-mcp configure` to obtain actual launch fields.
See [the usage guide](../USAGE.md). No desktop-client version is certified yet.

`claude-desktop.template.json` illustrates a local stdio launch through a dedicated
Python environment with Pinak's MCP extra installed. The path is to Python itself,
not a shell activation script. On Windows use escaped backslashes or forward
slashes. Each host chooses its own format; this is not a universal MCP config.

`pinak-mcp.template.json` follows the implemented version 1 policy. Unknown fields are rejected
with a helpful migration message. Paths refer to the user's machine; configuration
belongs outside the repository in the user's application config directory.

Keep server_name fixed as Pinak-MCP in runtime code; it need not be an editable
user setting. `config_schema_version` tracks config evolution, not package release.
