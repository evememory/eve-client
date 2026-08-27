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
- [ ] Run diff-scoped Ruff lint and format verification.
- [ ] Run quality and security reviews and resolve accepted findings.
- [ ] Run an isolated Hermes profile end-to-end test.
- [ ] Merge the client branch.
- [ ] Tag and publish `eve-memory-client@0.3.5`.
- [ ] Verify the public package and document the release receipt.

## Review

- Scope stays limited to one explicit Hermes profile.
- No Auth0, GCP, YAML, token, or bulk-profile mutation is allowed.
- Release is complete only after the public 0.3.5 package is verified.
