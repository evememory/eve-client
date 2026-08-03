# Eve Memory For Claude Code

This plugin packages Eve Memory MCP setup, Claude Code hooks, and usage instructions.

## Data Handling

Eve Memory stores project context, preferences, decisions, and learned rules on
Eve's hosted servers. It also stores conversation data:

- Session start and end logs (summaries and metadata) are recorded on Eve's servers.
- Before context compaction, the conversation is sent to Eve's servers and
  distilled into memories by a third-party AI model (Google Gemini via Google
  Cloud Vertex AI).
- Transcript text passed to the extraction tool is sent to Eve and stored.

Conversation summaries, session logs, and episodic memory entries can be viewed
and deleted in your Eve workspace at https://evemem.com/app. Semantic memories
can be deleted with the memory_forget tool. All other stored data is viewable
in the workspace; see https://evemem.com/privacy for deletion requests.

See https://evemem.com/privacy for the full policy, including the list of AI
subprocessors.

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
