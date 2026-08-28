# Local MCP Bridge SDK 2 Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` during implementation and
> `superpowers:verification-before-completion` before release. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release `eve-memory-client` 0.3.8 with the optional local
`eve-mcp-server` bridge on MCP Python SDK 2.x.

**Architecture:** Keep MCP out of the base package. Change only the optional
stdio bridge from `FastMCP` to `MCPServer`, and report the Eve package version
as the server version. Use the official SDK 2 client to prove modern and legacy
protocol behavior. Do not change hosted Eve calls or the native Hermes
provider.

**Tech Stack:** Python 3.11+, MCP Python SDK 2.x, httpx, pytest, uv.

**Spec:** `docs/specs/2026-08-28-mcp-python-sdk-v2.md`

## Global constraints

- Modify only the local bridge, its optional dependency, its tests, and release
  documentation.
- Keep the base package free of any MCP SDK requirement.
- Keep the existing `httpx` proxy client. Do not route it through `httpx2`.
- Preserve all current tool contracts and the stdio command.
- Do not add a dual SDK compatibility shim.

---

### Task 1: Freeze SDK 2 server behavior with failing tests

**Files:**
- Create: `tests/test_server.py`
- Create: `tests/fixtures/eve_mcp_server_tools_v1.json`
- Read: `eve_client/server.py`

**Interfaces:**
- Consumes: `eve_client.server.mcp`.
- Consumes: `mcp.client.Client` with `mode="auto"` and `mode="legacy"`.
- Consumes: `mcp.client.stdio.stdio_client` and
  `mcp.client.stdio.StdioServerParameters`.

- [ ] **Step 1: Add the module import test**

Import `eve_client.server` in a test environment with `mcp>=2,<3`. The current
code must fail because `mcp.server.fastmcp` does not exist.

- [ ] **Step 2: Freeze the complete SDK 1 tool descriptors**

Capture the current SDK 1 `tools/list` descriptors as canonical JSON in
`tests/fixtures/eve_mcp_server_tools_v1.json`. Keep `name`, `description`,
`inputSchema`, and `outputSchema` for every tool. Sort keys and tool names. The
test must serialize with `ensure_ascii=False` and separators `(",", ":")`.
The verified 13-tool payload is 17,260 bytes with SHA-256
`4285be8c0225dcb9375587f8ece2ce36eddb1363a77f735fee2d60ad060e3e4d`.

- [ ] **Step 3: Add in-process protocol tests**

Parametrize the official SDK 2 `Client` across `"auto"` and `"legacy"`.
Compare each returned tool's `name`, `description`, `input_schema`, and
`output_schema` with the frozen SDK 1 fixture. Assert that `server_info.version`
equals `eve_client.__version__`. Replace `_proxy` with an async sentinel and
call `memory_search`. Assert the proxy receives the same tool name and
arguments in both modes and that the text result is unchanged.

- [ ] **Step 4: Add installed-command stdio tests**

Launch `eve-mcp-server` with `stdio_client` in both client modes. Assert that
the subprocess returns the frozen descriptors and the Eve package version.
Then call `memory_search` and assert the existing
`authentication_required` text result. Give the child a temporary `HOME` and
`XDG_STATE_HOME`, set
`PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`, and do not pass a real
credential. This proves stdio `tools/call` without a hosted request.

- [ ] **Step 5: Run the narrow tests and confirm the expected failure**

Run:

```bash
uv run --with pytest --with 'mcp>=2,<3' \
  python -m pytest tests/test_server.py -q
```

Expected: collection fails on the removed `mcp.server.fastmcp` import.

- [ ] **Step 6: Commit the failing tests and fixture**

```bash
git add tests/test_server.py tests/fixtures/eve_mcp_server_tools_v1.json
git commit -m "test: define MCP SDK 2 bridge behavior"
```

### Task 2: Perform the minimal SDK migration

**Files:**
- Modify: `eve_client/server.py:17-25`
- Modify: `pyproject.toml:31-32`
- Modify: `tests/test_distribution.py`

**Interfaces:**
- Replaces: `from mcp.server.fastmcp import FastMCP`.
- Produces: `from mcp.server import MCPServer`.
- Consumes: `eve_client._version.__version__`.
- Produces: `MCPServer(..., version=__version__)`.
- Replaces optional requirement: `mcp>=1.20,<2`.
- Produces optional requirement: `mcp>=2,<3`.

- [ ] **Step 1: Change only the server class import and construction**

Import `MCPServer` from `mcp.server` and `__version__` from
`eve_client._version`. Construct the existing `mcp` object with
`version=__version__`. Keep the name, instructions, decorators, asynchronous
handlers, and `mcp.run(transport="stdio")` unchanged.

- [ ] **Step 2: Move the optional dependency to SDK 2**

Set the `server` extra to `mcp>=2,<3`. Keep `httpx>=0.27`. Do not add MCP to
base dependencies and do not pin `mcp-types` separately.

- [ ] **Step 3: Update distribution assertions**

Change the wheel-metadata assertion to require
`mcp<3,>=2; extra == 'server'`. Keep the assertion that no base requirement
starts with `mcp`. Keep the isolated `[server]` import test.

- [ ] **Step 4: Run the focused test gate**

Run:

```bash
uv run --with pytest --with 'mcp>=2,<3' \
  python -m pytest tests/test_server.py tests/test_distribution.py -q
```

Expected: all focused tests pass. Both client modes report the frozen tool
descriptors, the Eve package version, and the representative tool result over
in-process and stdio transports.

- [ ] **Step 5: Inspect the exact diff for unnecessary changes**

Run:

```bash
git diff --check
git diff -- eve_client/server.py pyproject.toml \
  tests/test_server.py tests/test_distribution.py
```

Expected: no change outside the import, constructor name, explicit Eve server
version, optional dependency, and required tests.

- [ ] **Step 6: Commit the migration**

```bash
git add eve_client/server.py pyproject.toml \
  tests/test_server.py tests/test_distribution.py
git commit -m "fix: migrate local MCP bridge to SDK 2"
```

### Task 3: Verify and release 0.3.8

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/test_distribution.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `tasks/todo.md`

- [ ] **Step 1: Write the failing release-version expectation**

Change the distribution version test to expect 0.3.8. Run only that test and
confirm it fails while `pyproject.toml` still reports 0.3.7.

- [ ] **Step 2: Set version 0.3.8 and update bridge documentation**

Set the package version to 0.3.8. State that `[server]` now uses MCP SDK 2 and
that base installs still do not install or replace a host MCP SDK. Update the
changelog and task ledger with only this migration.

- [ ] **Step 3: Run the complete automated gate**

Run:

```bash
NO_COLOR=1 TERM=dumb uv run --with pytest --with pytest-cov \
  --with 'mcp>=2,<3' \
  python -m pytest --cov=eve_client --cov-report=term-missing -q tests
```

Expected: zero failures and repository coverage at or above the current 83%.

- [ ] **Step 4: Build and inspect release artifacts**

Run:

```bash
bash scripts/publish-eve-client-pypi.sh --dry-run \
  --dist-dir /tmp/eve-memory-client-0.3.8-dist
unzip -p /tmp/eve-memory-client-0.3.8-dist/*.whl '*/METADATA' \
  | rg '^(Name|Version|Requires-Dist):'
```

Expected: version 0.3.8, no base MCP requirement, and only
`mcp<3,>=2; extra == 'server'`.

- [ ] **Step 5: Run disposable host-compatibility proofs**

In one clean environment, install MCP 2.x and the base wheel; confirm the MCP
version is not replaced and the native Hermes provider imports. In another
clean environment, install the wheel with `[server]`; run the stdio modern and
legacy discovery tests against the installed command.

- [ ] **Step 6: Run independent quality and security reviews**

Review the exact release diff. Fix accepted findings, rerun affected tests, and
repeat review until no accepted finding remains. Use the approved secondary
Codex review path if Council is unavailable or intentionally skipped.

- [ ] **Step 7: Commit and publish**

Commit the exact reviewed release candidate, merge it to client `main`, and
create annotated tag `eve-memory-client@0.3.8`. Wait for all release workflow
jobs to pass.

- [ ] **Step 8: Verify the public package**

Run:

```bash
uvx --refresh --index-url https://pypi.org/simple \
  --from 'eve-memory-client==0.3.8' eve version
```

Expected output: `0.3.8`. Confirm public wheel metadata has no base MCP
requirement and has the SDK 2 server extra.

## Self-review

- Scope: Only the optional local bridge migrates. Hosted Eve, OAuth, Hermes,
  and the native provider remain unchanged.
- Simplicity: The production change is one import rename, one version import,
  one constructor rename with an explicit version, and one optional dependency
  range.
- Compatibility: Tests cover SDK 2 modern and legacy protocol paths, in-process
  calls, and the installed stdio command.
- Silent defaults: The plan chooses `mcp>=2,<3`, a one-way migration, and patch
  release 0.3.8. These choices are explicit in the spec.
