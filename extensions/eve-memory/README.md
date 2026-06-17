# Eve Memory for Gemini CLI

This Gemini CLI extension connects Gemini CLI to Eve Memory through Eve's hosted MCP endpoint.

## Status

This package is an install artifact for PACK-12 validation. It is not promoted until clean install, connect, store, read, forget, attribution, and rollback evidence pass from a clean Gemini CLI environment.

## Install

From a local checkout during validation:

```bash
gemini extensions install ./extensions/eve-memory
```

From a release source after publishing:

```bash
gemini extensions install https://github.com/evememory/eve-client
```

Restart Gemini CLI after installing the extension. Gemini CLI only reflects extension changes on startup.

## What It Adds

- Hosted MCP server: `https://mcp.evemem.com/mcp`
- Source attribution header: `X-Source-Agent: gemini_cli`
- Eve usage guidance from `GEMINI.md`

No API key or token is embedded in this package. Authentication must happen through Eve's supported MCP/auth flow or a separately configured Eve client path.

## Verify

Inside Gemini CLI:

```text
/extensions list
/mcp list
```

Before promotion, run a clean store/read/forget smoke from Gemini CLI and verify `connector.install.completed` plus `signup_source` attribution.

## Uninstall

```bash
gemini extensions uninstall eve-memory
```
