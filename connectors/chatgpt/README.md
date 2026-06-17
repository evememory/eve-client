# Eve Memory ChatGPT MCP App / Connector

Eve is an internet-hosted MCP service. The ChatGPT validation path uses the
hosted MCP endpoint:

```text
https://mcp.evemem.com/mcp
```

## Source-Tracked Connect

Use the source-tagged managed connect URL when ChatGPT is the first touch:

```text
https://evemem.com/app/connect?install_source=chatgpt-app
```

## Developer-Mode Validation

Before public submission, validate Eve from a ChatGPT workspace or account that
supports custom MCP apps/connectors:

1. create or import the custom MCP app/connector
2. use `https://mcp.evemem.com/mcp` as the MCP endpoint
3. complete the approved Eve auth flow
4. confirm Eve tools are visible in ChatGPT
5. store one non-secret memory
6. read or search the same memory
7. forget the smoke memory
8. disconnect or remove the app/connector

## Release Gate

Do not submit for public listing until all of these pass:

- developer-mode import
- supported auth confirmation
- tool visibility check
- clean store/read/forget smoke
- install-source attribution
- `connector.install.completed` telemetry
- disconnect or rollback proof
- privacy, terms, and tool-behavior copy review

No API key or token is embedded in this connector path.

