# Eve Memory Channel Status

This repo contains the public client and distribution artifacts for connecting
AI tools to Eve Memory.

## Current Channels

| Channel | Public artifact | Status |
| --- | --- | --- |
| Claude Code | `plugins/claude-code/` | Package ready; official marketplace submission in progress |
| Claude Desktop / claude.ai | `connectors/claude-desktop/` | Remote MCP connector path ready for host smoke and submission |
| Codex | `plugins/codex/` and `.agents/plugins/marketplace.json` | Codex-native plugin package ready; official listing path pending |
| ChatGPT | `connectors/chatgpt/` | Hosted MCP app/connector path ready for developer-mode validation |
| Gemini CLI | `extensions/eve-memory/` | Extension package ready; host action smoke pending |
| Cursor | `eve_client/integrations/cursor.py` | Installer/provider support present; host smoke pending |
| VS Code | `eve_client/integrations/vscode.py` | Installer/provider support present; host smoke pending |
| Windsurf / Devin Desktop | `eve_client/integrations/windsurf.py` | Provider present; host identity/listing path needs re-verification |

## Promotion Rule

A channel is not promoted from package validation alone.

Before a channel is promoted, it must pass clean-host smoke:

1. install or import the channel artifact
2. connect to Eve through the supported auth path
3. store one non-secret memory
4. read or search that memory
5. forget the smoke memory
6. prove install-source attribution
7. prove rollback or uninstall

## Hosted MCP Endpoint

All remote-host paths use Eve's hosted MCP endpoint:

```text
https://mcp.evemem.com/mcp
```

No plugin, extension, or connector artifact in this repo embeds API keys,
bearer tokens, passwords, or private credentials.

## Submission Notes

- Claude Code and Codex use plugin packages from this repo.
- Claude Desktop / claude.ai and ChatGPT use Eve's hosted MCP endpoint.
- Marketplace or directory submission can require owner/admin access in the
  target platform. Those steps are external to this repository.

