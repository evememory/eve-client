# Changelog

This file records notable changes to `eve-memory-client`.

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
