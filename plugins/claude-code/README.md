# Eve Memory For Claude Code

This plugin packages Eve Memory MCP setup, Claude Code hooks, and usage instructions.

## Requirements

- `eve-memory-client` installed and on `PATH`
- Eve account connected with `eve connect`
- Claude Code with plugin support

## Source-Tracked Install

Use the source-tagged installer when this plugin is the first touch:

```bash
curl -fsSL "https://evemem.com/install?install_source=claude-code-plugin" -o install-eve.sh
sh install-eve.sh
eve connect --tool claude-code --install-source claude-code-plugin
```

## Verify

```bash
eve verify --tool claude-code
```

## Plugin Package

This directory is the Claude Code plugin package. It includes:

- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `.mcp.json`
- Eve Memory skill instructions
- Claude Code hook definitions

The plugin package embeds no Eve API key, bearer token, password, or private
credential.

## Runtime Path

The plugin starts `eve-mcp-server`, which reads local Eve credentials and proxies tool calls to the hosted MCP endpoint:

```text
https://mcp.evemem.com/mcp
```

No API key or token is embedded in the plugin files.

## Rollback

Disable or uninstall the Claude Code plugin, then run:

```bash
eve uninstall --tool claude-code
```

The uninstall path removes only Eve-owned config blocks and credentials.
