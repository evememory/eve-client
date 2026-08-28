# Local MCP Bridge SDK 2 Migration

Status: Proposed. Implementation requires approval.

## Goal

Move the optional local `eve-mcp-server` bridge from MCP Python SDK 1.x to the
stable MCP Python SDK 2.x line.

The target release is `eve-memory-client` 0.3.8.

## Current state

- The base `eve-memory-client` package does not depend on the MCP Python SDK.
- The optional `server` extra requires `mcp>=1.20,<2`.
- `eve_client/server.py` imports `FastMCP` from
  `mcp.server.fastmcp`. MCP SDK 2 removes this import path.
- The bridge uses decorators, asynchronous tool handlers, and stdio transport.
  It does not use MCP resources, prompts, sampling, elicitation, roots, or
  server-side HTTP transport.

## Required behavior

1. Change the optional `server` extra to `mcp>=2,<3`.
2. Keep the base package free of an MCP SDK dependency.
3. Replace `FastMCP` with `MCPServer` from `mcp.server`.
4. Set `MCPServer.version` to the installed `eve-memory-client` version. Do not
   accept the SDK 2 empty-string default.
5. Preserve the `eve-mcp-server` command and stdio transport.
6. Preserve all current tool names, input schemas, descriptions, proxy calls,
   and text results.
7. Support both MCP protocol paths supplied by SDK 2:
   - the current 2026-07-28 path;
   - the legacy initialize-handshake path.
8. Keep the bridge's direct hosted-Eve HTTP calls on its declared `httpx`
   dependency. Do not change them to `httpx2`; no SDK HTTP client object crosses
   this boundary.
9. Do not write non-protocol output to stdout while the stdio server runs.

The current tool set is:

- `memory_search`
- `memory_store`
- `memory_extract`
- `memory_forget`
- `memory_update`
- `memory_session_start`
- `memory_session_end`
- `memory_get_preferences`
- `memory_feedback`
- `memory_ingest`
- `memory_ingest_url`
- `memory_ingest_status`
- `memory_pre_compact`

## Acceptance tests

Automated tests must prove:

- the module imports with MCP SDK 2;
- a modern SDK 2 client lists the exact current tool set;
- an SDK 2 client in legacy mode lists the same tool set;
- both modes report the installed `eve-memory-client` version as the server
  version;
- the complete canonical tool descriptors match the frozen SDK 1 fixture,
  including every name, description, input schema, and output schema;
- one representative in-process tool call preserves the current `_proxy`
  contract in both modes;
- the installed `eve-mcp-server` subprocess answers `tools/list` over stdio in
  both modes;
- the same subprocess completes one no-network `tools/call` in both modes;
- the built base wheel has no MCP requirement;
- the built wheel with `[server]` installs MCP 2.x and imports the server;
- the full Eve client suite and release artifact checks pass.

## Scope boundaries

- No change to the hosted Eve MCP endpoint.
- No change to the Hermes OAuth connector.
- No change to the native Hermes memory provider.
- No change to Hermes Agent.
- No dual SDK 1.x and 2.x compatibility layer.
- No new transport, tool, auth path, retry policy, or proxy abstraction.
- No change to tool semantics or hosted API payloads.

## Defaults taken

- Use `mcp>=2,<3`, not an exact MCP patch pin. This follows the SDK's supported
  stable major line while blocking a future breaking major.
- Make a clean one-way migration for the optional bridge. Do not add import
  fallbacks for both SDK majors.
- Report the Eve package version through `serverInfo.version`. Do not inherit
  SDK 1's SDK-version default or SDK 2's empty-string default.
- Release as 0.3.8 because this is a compatibility correction to an optional
  component and does not change the base client or hosted service.

## Official references

- <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md>
- <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md>
- <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/legacy-clients.md>
- <https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md>
