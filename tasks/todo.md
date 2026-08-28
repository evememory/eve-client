# MCP SDK 2 local bridge and 0.3.8 release

- [x] Define SDK 2 bridge behavior for modern and legacy client modes.
- [x] Migrate only the optional local `eve-mcp-server` bridge to MCP SDK 2.
- [x] Keep MCP out of base dependencies and constrain the `server` extra to
  `mcp>=2,<3`.
- [x] Advance the distribution version expectation to 0.3.8.
- [x] Run the artifact and clean-install gates.
- [x] Complete the full test and coverage gate: 668 passed, 7 skipped, 84%
  coverage.

## Review

- Scope is limited to the optional local bridge and its package release record.
- Publication, tags, workflows, and remote systems are not part of this task.

# Hermes MCP dependency correction and 0.3.7 release

- [x] Reproduce the Hermes MCP SDK downgrade from the 0.3.6 base package.
- [x] Add a failing wheel-metadata regression test.
- [x] Remove the MCP SDK from base dependencies.
- [x] Keep the legacy MCP SDK in the optional `server` extra.
- [x] Run the complete test, coverage, build, and artifact gates.
- [x] Complete an independent secondary Codex review.
- [x] Tag and publish `eve-memory-client@0.3.7`.
- [x] Restore Hermes MCP 2.0 and install the public Eve 0.3.7 package.
- [x] Verify Hermes provider discovery without changing the active profile.

## Review

- Scope is limited to the package dependency correction.
- The hosted Eve MCP endpoint and native Hermes provider behavior do not change.
- The local `eve-mcp-server` bridge stays on MCP SDK 1.x until its separate
  migration is approved and implemented.

## Release receipt

- Client release commit: `252671cdd7029243f02dd22df9ab658f691f458c`.
- Tag: `eve-memory-client@0.3.7`.
- Workflow: <https://github.com/evememory/eve-client/actions/runs/33163549288>.
- GitHub release: <https://github.com/evememory/eve-client/releases/tag/eve-memory-client%400.3.7>.
- PyPI: <https://pypi.org/project/eve-memory-client/0.3.7/>.
- Verification: 662 passed, 7 skipped, and 83% total coverage.
- Public package proof: a fresh PyPI install returned `eve version` as `0.3.7`.
- Hermes proof: Eve 0.3.7 and MCP 2.0.0 are installed together. Hermes MCP
  imports use `httpx2`, dependency checks pass, and Eve provider discovery
  passes without changing the active profile.
- Review: the independent secondary Codex review approved the exact release
  candidate with no findings.

---

# Hermes native memory provider and 0.3.6 release

- [x] Freeze the adapter scope against Hermes 0.20.5 and Eve MCP contracts.
- [x] Implement the provider through the official Hermes entry-point contract.
- [x] Keep native API-key setup separate from the existing MCP OAuth path.
- [x] Add unit, transport, discovery, distribution, and lifecycle tests.
- [x] Verify the built wheel in a disposable Hermes profile.
- [x] Complete independent code-quality and security reviews.
- [x] Run the final 0.3.6 test, coverage, build, and artifact gates.
- [x] Merge the adapter into client `main`.
- [x] Tag and publish `eve-memory-client@0.3.6`.
- [x] Verify the public package and record the release receipt.

## Review

- Scope is limited to the native Hermes Eve adapter.
- Hermes core and the existing Eve MCP OAuth path remain unchanged.
- Release is complete only after the exact public 0.3.6 package is verified.

## Release receipt

- Client commit: `66d45d973a19180680f4eab58264b5d0f0ab609f`.
- Tag: `eve-memory-client@0.3.6`.
- Workflow: <https://github.com/evememory/eve-client/actions/runs/33162000017>.
- GitHub release: <https://github.com/evememory/eve-client/releases/tag/eve-memory-client%400.3.6>.
- PyPI: <https://pypi.org/project/eve-memory-client/0.3.6/>.
- Verification: 660 passed, 7 skipped, and 83% total coverage. Provider
  coverage is 96%; transport coverage is 97%.
- Package proof: the public package returned `eve version` as `0.3.6`.
- Hermes proof: official 0.20.5 discovery and built-wheel setup in a disposable
  profile passed.
- Review: independent code-quality and security review approved the adapter;
  the final secondary Codex release review approved the corrected release
  metadata and documentation.

---

# Hermes profile OAuth and 0.3.5 release

- [x] Confirm affected Hermes version is 0.20.5.
- [x] Confirm live Auth0 CIMD and offline-access prerequisites.
- [x] Approve the narrow named-profile design.
- [x] Create an isolated `eve-client` branch from current `origin/main`.
- [x] Write the implementation spec and plan.
- [x] Implement the Hermes runtime boundary with TDD.
- [x] Wire `connect` and `verify` with TDD.
- [x] Update documentation and package version to 0.3.5.
- [x] Run the complete automated test suite.
- [x] Confirm total test coverage is 82%.
- [x] Run the dry-run 0.3.5 release build and artifact checks.
- [x] Record repository-wide Ruff baseline failures (213 lint errors; 72 files unformatted).
- [x] Run diff-scoped Ruff lint and format verification (new files pass; two `cli.py` F401 findings match `origin/main`).
- [x] Run quality and security reviews and resolve accepted findings.
- [x] Run an isolated Hermes profile end-to-end test.
- [x] Merge the client branch.
- [x] Tag and publish `eve-memory-client@0.3.5`.
- [x] Verify the public package and document the release receipt.

## Review

- Scope stays limited to one explicit Hermes profile.
- No Auth0, GCP, YAML, token, or bulk-profile mutation is allowed.
- Release is complete only after the public 0.3.5 package is verified.

## Release receipt

- Client commit: `93bc6bb8fd1a996a7280ed6ab140a7ada97f2fa3`.
- Tag: `eve-memory-client@0.3.5`.
- Workflow: <https://github.com/evememory/eve-client/actions/runs/33075121815>.
- PyPI: <https://pypi.org/project/eve-memory-client/0.3.5/>.
- Quality review: `0e4758e9-2b63-467e-91bd-3123e53b5685`.
- Security review: `9d1f663f-a370-4124-807b-7aa48260ff5e`.
- Live proof: Hermes OAuth, 15-tool discovery, verification, and a disposable
  store-search-delete round trip passed.
