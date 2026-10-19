# Proposed configuration examples

These are nonfunctional templates for phase 05, not current installation files.
Angle-bracket placeholders must be resolved and validated by the implementation.
Do not copy them into a live client expecting Pinak-MCP to exist yet.

`claude-desktop.template.json` illustrates a local stdio launch through a dedicated
Python environment with Pinak's MCP extra installed. The path is to Python itself,
not a shell activation script. On Windows use escaped backslashes or forward
slashes. Each host chooses its own format; this is not a universal MCP config.

`pinak-mcp.template.json` is the proposed user policy/config contract. Freeze and
implement a real schema before consuming it. Unknown fields should be rejected
with a helpful migration message. Paths refer to the user's machine; configuration
belongs outside the repository in the user's application config directory.

Keep server_name fixed as Pinak-MCP in runtime code; it need not be an editable
user setting. `config_schema_version` tracks config evolution, not package release.
