# Hermes native memory provider and 0.3.6 release

- [x] Freeze the adapter scope against Hermes 0.20.5 and Eve MCP contracts.
- [x] Implement the provider through the official Hermes entry-point contract.
- [x] Keep native API-key setup separate from the existing MCP OAuth path.
- [x] Add unit, transport, discovery, distribution, and lifecycle tests.
- [x] Verify the built wheel in a disposable Hermes profile.
- [x] Complete independent code-quality and security reviews.
- [x] Run the final 0.3.6 test, coverage, build, and artifact gates.
- [ ] Merge the adapter into client `main`.
- [ ] Tag and publish `eve-memory-client@0.3.6`.
- [ ] Verify the public package and record the release receipt.

## Review

- Scope is limited to the native Hermes Eve adapter.
- Hermes core and the existing Eve MCP OAuth path remain unchanged.
- Release is complete only after the exact public 0.3.6 package is verified.

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
