# Changelog

This file records notable changes to `eve-memory-client`.

## [0.3.7] - 2026-08-28

### Fixed

- Removed the legacy MCP Python SDK from the base package dependencies. A base
  install no longer replaces the MCP SDK supplied by Hermes.
- Kept `mcp>=1.20,<2` in the optional `server` extra for the local
  `eve-mcp-server` bridge. Its SDK 2 migration is a separate change.

### Compatibility

- The native Hermes memory provider and the base Eve CLI do not require the MCP
  Python SDK.
- The hosted Eve MCP endpoint and Hermes OAuth connector are unchanged.

### Verification

- Passed 662 tests with 7 skipped and 83% total coverage.
- Verified that installing the base 0.3.7 wheel into an environment with
  `mcp==2.0.0` keeps MCP at version 2.0.0.
- Passed the release artifact build and package checks.

### Release references

- Git tag: `eve-memory-client@0.3.7` (pending)
- PyPI: `eve-memory-client` 0.3.7 (pending)
- Release workflow: pending

## [0.3.6] - 2026-08-28

### Added

- Added the native Eve memory provider for Hermes Agent.
- Added package entry-point discovery through
  `hermes_agent.memory_providers`.
- Added bounded automatic recall, pre-compaction preservation, and session-end
  extraction.

### Safety and reliability

- Kept native-provider API-key setup separate from the existing Hermes MCP
  OAuth connector.
- Limited automatic recall and writes to the primary Hermes agent context.
- Scoped asynchronous recall to the current session and generation.
- Added bounded HTTP timeouts, a 1 MiB response limit, and no automatic retry
  loop.

### Verification

- Passed 660 tests with 7 skipped and 83% total coverage.
- Verified provider discovery with Hermes 0.20.5.
- Verified setup from the built wheel in a disposable Hermes profile.

### Release references

- [Git tag](https://github.com/evememory/eve-client/releases/tag/eve-memory-client%400.3.6)
- [PyPI package](https://pypi.org/project/eve-memory-client/0.3.6/)
- [Release workflow](https://github.com/evememory/eve-client/actions/runs/33162000017)
- [Hermes setup](README.md#hermes-cli)

## [0.3.5] - 2026-08-27

### Added

- Added explicit named-profile support for Hermes Agent 0.20.5 and newer.
- Added `eve connect --tool hermes --profile <name>` for OAuth setup and
  reauthentication.
- Added `eve verify --tool hermes --profile <name>` for profile-scoped MCP
  verification.

### Safety and reliability

- Kept Hermes profile configuration and OAuth tokens under the official Hermes
  CLI. The Eve client does not read or write Hermes YAML or tokens.
- Added semantic success checks for Hermes commands that can print an error but
  return exit code zero.
- Added regression tests for missing, conflicting, and failed profile-scoped
  MCP operations.

### Verification

- Passed 559 tests with 6 skipped and 82% total coverage.
- Verified browser OAuth, discovery of all 15 Eve MCP tools, and a live
  store-search-delete round trip with a disposable Hermes profile.

### Release references

- [Git tag](https://github.com/evememory/eve-client/releases/tag/eve-memory-client%400.3.5)
- [PyPI package](https://pypi.org/project/eve-memory-client/0.3.5/)
- [Release workflow](https://github.com/evememory/eve-client/actions/runs/33075121815)
- [Implementation spec](docs/specs/2026-08-27-hermes-profile-oauth.md)

Earlier versions remain available through the repository tags and PyPI release
history.
