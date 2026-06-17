---
name: eve-memory
description: Use Eve Memory from Claude Code to retrieve prior context and preserve durable project decisions.
---

# Eve Memory

Use Eve when the task depends on prior project decisions, user preferences, or continuity across sessions.

Before assuming context is unavailable, call Eve search or read tools if they are configured.

Store only durable, non-secret information. Do not store API keys, passwords, private tokens, or credentials.

For setup or repair, run:

```bash
eve verify
```
