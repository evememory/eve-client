# Hermes interactive Eve tools

Status: implemented and verified on the feature branch; not released or installed.
Tracks eve-client issue #4. Verification and review: [task record](../../tasks/todo.md).

## Contract

- Expose only `eve_search` and `eve_store` through the existing Hermes provider.
  Use Hermes function schemas and return JSON strings from `handle_tool_call`.
- Search accepts query (1–2000 characters), optional context, store, limit (1–20),
  and min_similarity (0–1). Defaults: configured context, `all` stores, configured
  recall_limit and min_similarity. Stores: semantic, episodic, preference,
  learned_rules, all. Explicit context `all` searches across contexts.
- Store accepts content (1–10000 characters), optional context and store.
  Default: configured context and semantic. Only semantic and episodic writes.
  Map content to memory_store.text; source and source_agent are hermes_agent;
  session_id comes from the active provider. Preserve the exact content.
- Accept custom context names under Eve's existing name rules. Reject `all` as
  a write context and EPHEMERAL as persistent scope. The server remains the
  authority for tenant/context permissions. Explicitly use PERSONAL visibility.
- Reject unknown tools, unsupported arguments, invalid types/ranges, blank input,
  and calls on inactive/non-primary providers before network access. Do not allow
  model arguments to override source, session provenance, or visibility.
- Use the existing transport/request timeout and add only memory_store to its
  allowlist. No retries or new configuration. Return the server result unchanged
  as JSON; return redacted JSON errors on failure. A write transport failure must
  state that completion is unconfirmed, not claim a save or encourage blind retry.
- Interactive calls work with auto_recall disabled. Snapshot active session state
  under the existing lock; do not hold it during HTTP. Reject results if session
  state changes while a call is in flight; writes may already have completed.
- Static provider instructions explain tool usage, profile context defaults,
  preference versus semantic search, untrusted retrieved content, write receipts,
  and the semantic/episodic-only write limitation. No network or credentials in
  prompt assembly.

## Boundaries and evidence

No Hermes core, OAuth connector, server, dependency, local-profile, retry queue,
built-in Markdown mirroring, dedicated preference/rule writes, delete/edit tools,
version bump, release, or local installation changes in this slice.

Use focused provider/transport tests for mapping, receipts, validation, errors,
scope, disabled auto recall, and session changes. Exercise package discovery and
tool calls against the installed Hermes contract with a fake HTTP boundary.
Update README and the unreleased changelog. Existing v1 plans remain historical.
