from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_FILES = (
    "plugins/claude-code/.claude-plugin/plugin.json",
    "plugins/claude-code/.mcp.json",
    "plugins/claude-code/hooks/hooks.json",
    "plugins/claude-code/skills/eve-memory/SKILL.md",
    "plugins/claude-code/README.md",
    "connectors/claude-desktop/README.md",
    "plugins/codex/.codex-plugin/plugin.json",
    "plugins/codex/.mcp.json",
    "plugins/codex/skills/eve-memory/SKILL.md",
    "plugins/codex/README.md",
    "extensions/eve-memory/gemini-extension.json",
    "extensions/eve-memory/GEMINI.md",
    "extensions/eve-memory/README.md",
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]


def validate_artifact_tree(root: Path) -> ValidationResult:
    errors = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    return ValidationResult(ok=not errors, errors=errors)


def main() -> int:
    result = validate_artifact_tree(Path.cwd())
    if result.ok:
        print("PACK-12 artifact tree: ok")
        return 0
    for error in result.errors:
        print(f"missing: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
