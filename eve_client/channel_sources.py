"""Channel/source attribution helpers for Eve client entry points."""

from __future__ import annotations

ALLOWED_INSTALL_SOURCES = frozenset(
    {
        "self_serve",
        "claude-code-plugin",
        "claude-desktop",
        "codex-plugin",
        "chatgpt-app",
        "install-button-cursor",
        "install-button-vscode",
        "gemini-cli-extension",
        "cursor",
        "vscode",
        "windsurf",
    }
)


def normalize_install_source(value: object, *, default: str | None = None) -> str | None:
    """Return an allowlisted install source or None."""

    if value is None or str(value).strip() == "":
        return default
    source = str(value).strip().lower()
    return source if source in ALLOWED_INSTALL_SOURCES else None

