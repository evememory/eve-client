# Eve Memory Claude Desktop / claude.ai Connector

Eve is an internet-hosted MCP service. The first connector path is remote MCP at:

```text
https://mcp.evemem.com/mcp
```

## Source-Tracked Connect

Use the source-tagged managed connect URL when this connector is the first touch:

```text
https://evemem.com/app/connect?tool=claude-desktop&install_source=claude-desktop
```

## Required Smoke

1. Add Eve as a Claude connector using the hosted MCP endpoint.
2. Complete OAuth or the approved hosted auth flow.
3. Store one non-secret memory.
4. Read or search the same memory.
5. Forget the smoke memory.

## Release Gate

Do not submit to the Anthropic connector directory unless all of these pass:

- OAuth/account-selection smoke
- tool annotations audit
- privacy policy review
- clean store/read/forget smoke
- allowed-links review if the connector opens links

## MCPB Fallback

Build an MCPB desktop extension only if remote MCP cannot satisfy the first-wave release path or an enterprise desktop distribution path requires a local bundle.

Remote MCP is first because Eve is hosted; MCPB is a fallback, not the default artifact.
