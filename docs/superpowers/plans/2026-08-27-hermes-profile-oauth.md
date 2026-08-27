# Hermes Named-Profile OAuth Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release `eve-memory-client` 0.3.5 with safe, explicit Hermes named-profile setup and OAuth recovery.

**Architecture:** Add one focused `eve_client/hermes.py` boundary that validates Hermes and invokes only official profile-scoped commands. Wire it into the existing `connect` and `verify` commands with explicit `--profile` handling. Do not route Hermes through the file-based plan, credential, manifest, or rollback engine.

**Tech Stack:** Python 3.11+, Typer, `subprocess`, JSON, pytest, uv, GitHub Actions trusted PyPI publishing.

**Spec:** `docs/specs/2026-08-27-hermes-profile-oauth.md`

## Global Constraints

- Require Hermes Agent 0.20.5 or newer.
- Require one explicit existing profile matching `^[a-z0-9][a-z0-9_-]{0,63}$`.
- Use server name `eve-memory` and endpoint `https://mcp.evemem.com/mcp`.
- Never read or write Hermes YAML.
- Never read, log, return, or store Hermes OAuth tokens.
- Never create or modify an Auth0 application.
- Never include Hermes in an implicit `--all` operation.
- Invoke subprocesses with argument arrays and no shell.

---

### Task 1: Hermes runtime boundary

**Files:**
- Create: `eve_client/hermes.py`
- Create: `tests/test_hermes.py`

**Interfaces:**
- Produces: `HermesIntegrationError(RuntimeError)`.
- Produces: `parse_hermes_version(output: str) -> tuple[int, int, int]`.
- Produces: `validate_hermes_profile(profile: str | None) -> str`.
- Produces: `connect_hermes_profile(profile: str, mcp_base_url: str, server_name: str = "eve-memory") -> str`, returning `"added"` or `"reauthenticated"`.
- Produces: `verify_hermes_profile(profile: str, mcp_base_url: str, server_name: str = "eve-memory") -> None`.

- [ ] **Step 1: Write failing version and profile tests**

Add tests that assert the exact v0.20.5 output parses to `(0, 20, 5)`, an older version fails, missing or malformed profiles fail, and `team_1` is accepted.

- [ ] **Step 2: Run the narrow tests and confirm failure**

Run:

```bash
uv run --with pytest python -m pytest tests/test_hermes.py -q
```

Expected: collection fails because `eve_client.hermes` does not exist.

- [ ] **Step 3: Add minimal validation and command helpers**

Implement the constants and public functions above. Use
`shutil.which("hermes")`, `subprocess.run([...])`, and `json.loads`. Check the
profile with `hermes profile show <profile>`. Read the MCP entry only through
`hermes --profile <profile> config get mcp_servers.<server> --json`.

- [ ] **Step 4: Add failing routing tests**

Mock `subprocess.run` and assert:

```python
["hermes", "--profile", "team_1", "mcp", "login", "eve-memory"]
```

for an exact existing entry, and:

```python
[
    "hermes", "--profile", "team_1", "mcp", "add", "eve-memory",
    "--url", "https://mcp.evemem.com/mcp", "--auth", "oauth",
]
```

for a missing entry. Assert a conflicting entry invokes neither mutation.

- [ ] **Step 5: Implement minimal add, login, post-check, and test behavior**

The profile-scoped add and login commands inherit the terminal. A non-zero
exit raises `HermesIntegrationError`. After add or login, repeat the JSON entry
read and require the exact URL, OAuth auth mode, and `enabled` not false.
Verification invokes:

```python
["hermes", "--profile", profile, "mcp", "test", server_name]
```

- [ ] **Step 6: Run Task 1 tests**

Run:

```bash
uv run --with pytest python -m pytest tests/test_hermes.py -q
```

Expected: all Task 1 tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add eve_client/hermes.py tests/test_hermes.py
git commit -m "feat: add Hermes profile OAuth boundary"
```

### Task 2: CLI commands and user documentation

**Files:**
- Modify: `eve_client/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `connect_hermes_profile`, `verify_hermes_profile`, and `HermesIntegrationError` from Task 1.
- Produces: `eve connect --tool hermes --profile <name>`.
- Produces: `eve verify --tool hermes --profile <name>`.

- [ ] **Step 1: Write failing CLI tests**

Add tests that prove `connect` and `verify` require `--profile`, only accept
Hermes as the sole selected tool, call the Task 1 functions with the resolved
MCP endpoint, and convert `HermesIntegrationError` to exit code 1 without a
traceback or secret output.

- [ ] **Step 2: Run the CLI tests and confirm failure**

Run:

```bash
uv run --with pytest python -m pytest tests/test_cli.py -q
```

Expected: Hermes CLI cases fail because `--profile` and the Hermes branch are
not implemented.

- [ ] **Step 3: Add the explicit Hermes CLI branch**

Add `profile: str | None = typer.Option(None, "--profile")` to `connect` and
`verify`. Handle Hermes before the generic detector, plan, credential, and
verification paths. Require `--auth-mode oauth` when supplied. Print the named
profile and the result, but never print command output that can include an
authorization URL.

Reject `hermes` in generic `install`, `repair`, and `uninstall` commands with a
short instruction to use `eve connect --tool hermes --profile <name>`.

- [ ] **Step 4: Document the supported path**

Add a Hermes section to `README.md` with the version floor, named-profile
commands, OAuth ownership boundary, and upgrade command. State that existing
profiles use fresh reauthentication and that users do not need a fixed client
ID.

- [ ] **Step 5: Run Task 2 tests**

Run:

```bash
uv run --with pytest python -m pytest tests/test_cli.py tests/test_hermes.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add eve_client/cli.py tests/test_cli.py README.md
git commit -m "feat: support Hermes named profiles"
```

### Task 3: Version, release gates, and published-package proof

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/test_distribution.py`
- Modify: `README.md`
- Modify: `tasks/todo.md`

**Interfaces:**
- Produces: package and tag version `0.3.5`.
- Produces: trusted-publishing tag `eve-memory-client@0.3.5`.

- [ ] **Step 1: Write the release expectation**

Change the distribution test expectation from `0.3.4` to `0.3.5`, then run:

```bash
uv run --with pytest python -m pytest \
  tests/test_distribution.py::test_pack12_release_version_advances_beyond_published_0_3_0 -q
```

Expected: failure because `pyproject.toml` still reports 0.3.4.

- [ ] **Step 2: Bump the package and documentation to 0.3.5**

Set `[project].version = "0.3.5"`. Update current release examples in the
README. Do not change historical Pack 12 evidence that intentionally names
0.3.3.

- [ ] **Step 3: Run the complete automated test gate**

Run:

```bash
uv run --with pytest --with pytest-cov python -m pytest \
  --cov=eve_client --cov-report=term-missing -q tests
```

Expected: zero failures and coverage reported.

- [ ] **Step 4: Run formatting, lint, and release build checks**

Run:

```bash
uvx ruff check eve_client tests
uvx ruff format --check eve_client tests
bash scripts/publish-eve-client-pypi.sh --dry-run --dist-dir "$(mktemp -d)"
```

Expected: all commands exit zero and the dry run contains one 0.3.5 wheel and
one 0.3.5 source archive.

- [ ] **Step 5: Run required reviews and accept fixes**

Run Council quality and security reviews against the complete diff. Run a Sol
reviewer if Council is unavailable. Fix accepted findings and rerun affected
tests. Record the successful Council run ID in the final commit trailer.

- [ ] **Step 6: Run an isolated Hermes profile smoke test**

Use a disposable named profile. Install the built 0.3.5 wheel in an isolated
environment, run `eve connect --tool hermes --profile <disposable-profile>`,
complete browser authentication, then run `eve verify`. Confirm an Eve memory
write/read/retract round trip. Record only sanitized outcomes.

- [ ] **Step 7: Commit the release candidate**

```bash
git add pyproject.toml tests/test_distribution.py README.md tasks/todo.md \
  docs/specs/2026-08-27-hermes-profile-oauth.md \
  docs/superpowers/plans/2026-08-27-hermes-profile-oauth.md
git commit -m "release: prepare eve-memory-client 0.3.5"
```

Add:

```text
Council-Review: <successful-run-id>
```

- [ ] **Step 8: Merge and publish**

Push the branch, merge it into `evememory/eve-client` main, and verify the
exact merged SHA. Create and push the annotated tag
`eve-memory-client@0.3.5` on that SHA. Wait for every release workflow job to
pass.

- [ ] **Step 9: Verify the public release**

Confirm PyPI returns version 0.3.5 with one wheel and one source archive, then
run:

```bash
uvx --refresh --from "eve-memory-client==0.3.5" eve version
```

Expected output: `0.3.5`.

## Self-review

- Spec coverage: Every required behavior, boundary, test, and release gate is
  assigned to a task.
- Placeholder scan: No implementation step contains `TBD`, `TODO`, or an
  unspecified error-handling instruction.
- Type consistency: Task 2 consumes the exact four public names produced by
  Task 1. Task 3 changes only version and release surfaces.
- Silent defaults: The existing profile requirement, missing-versus-existing
  route, fail-closed conflict behavior, and exclusion from bulk operations are
  explicit in the spec.
