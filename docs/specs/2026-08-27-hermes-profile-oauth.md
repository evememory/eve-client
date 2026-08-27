# Hermes Named-Profile OAuth Support

Status: Approved for implementation on 2026-08-27.

## Goal

Add a safe Eve client command that configures and authenticates one explicit
Hermes Agent profile against the hosted Eve MCP endpoint.

The release version is `eve-memory-client` 0.3.5.

## User command

```bash
eve connect --tool hermes --profile <profile-name>
```

The user must name one existing Hermes profile. Eve must not select the sticky
default profile, create a profile, or modify every profile.

Verification uses:

```bash
eve verify --tool hermes --profile <profile-name>
```

## Required behavior

1. Require a local `hermes` binary at version 0.20.5 or newer.
2. Accept profile IDs that match Hermes: `^[a-z0-9][a-z0-9_-]{0,63}$`.
3. Confirm that the selected profile exists with the official Hermes CLI.
4. Inspect the selected profile's Eve MCP entry with:

   ```bash
   hermes --profile <profile-name> config get mcp_servers.eve-memory --json
   ```

5. If the entry does not exist, run:

   ```bash
   hermes --profile <profile-name> mcp add eve-memory \
     --url https://mcp.evemem.com/mcp \
     --auth oauth
   ```

6. If the exact Eve OAuth entry exists, run:

   ```bash
   hermes --profile <profile-name> mcp login eve-memory
   ```

   Hermes owns token deletion, browser authentication, CIMD client discovery,
   token storage, and refresh.

7. If an `eve-memory` entry exists with a different URL or auth mode, stop and
   show a clear error. Do not silently overwrite it.
8. After either connection path, read the entry again and require the exact
   hosted URL, `auth: oauth`, and an enabled state.
9. Verification runs the official profile-scoped command:

   ```bash
   hermes --profile <profile-name> mcp test eve-memory
   ```

10. Child Hermes processes inherit the user's terminal. Browser login and
    Hermes prompts stay visible and interactive.

## Security and ownership boundaries

- Eve client does not read or write Hermes YAML.
- Eve client does not read, return, log, or store Hermes OAuth tokens.
- Eve client does not accept or embed an Auth0 client ID or client secret.
- Eve client does not create, delete, or modify Auth0 applications.
- Eve client does not change GCP services or configuration.
- All subprocess calls use argument arrays. No shell command is constructed.
- Only the named profile is passed to Hermes.
- Hermes is excluded from implicit `--all` operations because a profile is
  mandatory.

## Errors

The command must fail before mutation when:

- `--profile` is missing or invalid;
- Hermes is missing;
- Hermes is older than 0.20.5;
- the named profile does not exist;
- the existing Eve entry is not the exact hosted OAuth entry.

The command must fail clearly when a Hermes command returns a non-zero status
or the post-command entry check is not exact. Error text must not include OAuth
tokens, callback state, authorization URLs, or full client IDs.

## Tests

Automated tests must prove:

- exact version parsing and version-floor enforcement;
- exact profile validation;
- missing-profile rejection;
- exact command argument arrays for add, login, and test;
- an existing correct entry selects login, not add;
- a missing entry selects add, not login;
- a mismatched entry stops before mutation;
- only the selected profile is used;
- the CLI requires `--profile` for Hermes;
- no Eve credential-store API is used;
- package and distribution version is 0.3.5.

Manual release validation must use a clean isolated Hermes profile and confirm
the browser flow, stored refresh capability, and an Eve MCP read/write round
trip. No token value is recorded in Git.

## Non-goals

- No Hermes profile creation or deletion.
- No bulk profile update.
- No Hermes YAML parser or writer.
- No replacement OAuth implementation in Eve client.
- No new Auth0 application.
- No Firebase or provider migration in this release.
- No refactor of the generic file-based installer action engine.

## Defaults taken

- The existing Hermes profile must already exist. Eve does not create it.
- A missing Eve entry uses `mcp add`; an exact existing entry uses `mcp login`.
- A conflicting entry fails closed instead of invoking an overwrite prompt.
- Hermes support is explicit through `connect` and `verify`; it is not included
  in generic `install --all`, `repair --all`, or `uninstall --all` operations.
