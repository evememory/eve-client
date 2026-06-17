# Eve Memory For Codex

This plugin packages Eve Memory instructions and hosted MCP setup for Codex.

## Requirements

- Codex with plugin support
- Eve account connected through the supported Codex OAuth or bearer-token flow

## Source-Tracked Install

Use the source-tagged installer when this plugin is the first touch:

```bash
curl -fsSL "https://evemem.com/install?install_source=codex-plugin" -o install-eve.sh
sh install-eve.sh
eve connect --tool codex-cli --auth-mode oauth --install-source codex-plugin
```

## Plugin Marketplace Install

The Codex plugin is exposed through this repo's Codex-native marketplace file:

```text
.agents/plugins/marketplace.json
```

From a local checkout:

```bash
codex plugin marketplace add /path/to/eve-client
codex plugin add eve-memory --marketplace eve-memory-codex
```

The marketplace entry points at:

```text
plugins/codex
```

## Runtime Path

The plugin points Codex at Eve's hosted MCP endpoint:

```text
https://mcp.evemem.com/mcp
```

No API key or token is embedded in the plugin files.

Codex should connect to Eve through the supported Eve OAuth or bearer-token
flow. Native `codex mcp login` is not the supported Eve path.

## Hooks

Codex hooks are not part of this v1 package. Add hooks only after the official Codex plugin hook contract is verified and separately tested.

## Rollback

Disable or uninstall the Codex plugin, then remove the Eve MCP entry from Codex settings if needed.

```bash
codex plugin remove eve-memory --marketplace eve-memory-codex
```
