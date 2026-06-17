from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_CHANNELS = {
    "claude-code-plugin": "claude-code-plugin",
    "claude-desktop": "claude-desktop",
    "codex-plugin": "codex-plugin",
    "chatgpt-app": "chatgpt-app",
}

REMAINING_REQUIRED_CHANNELS = {
    "install-button-cursor": "install-button-cursor",
    "install-button-vscode": "install-button-vscode",
    "gemini-cli-extension": "gemini-cli-extension",
    "cursor": "cursor",
    "vscode": "vscode",
    "windsurf": "windsurf",
}

REQUIRED_SMOKE_CHECKS = (
    "clean_environment",
    "entry_url",
    "install_or_import",
    "connect",
    "store",
    "read",
    "forget",
    "install_source_flow",
    "connector_install_completed",
    "rollback_or_uninstall",
)

VALID_CHECK_STATUSES = {"pass", "fail", "not_run", "blocked"}

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


@dataclass(frozen=True)
class SmokeMatrixValidationResult:
    ok: bool
    errors: list[str]


def _normalize_install_source(value: object) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    source = str(value).strip().lower()
    return source if source in ALLOWED_INSTALL_SOURCES else None


def _load_json(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"missing smoke matrix: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]

    if not isinstance(payload, dict):
        return None, ["smoke matrix must be a JSON object"]
    return payload, []


def _validate_smoke_matrix(
    path: Path,
    *,
    artifact_name: str,
    required_channels: dict[str, str],
) -> SmokeMatrixValidationResult:
    artifact, errors = _load_json(path)
    if artifact is None:
        return SmokeMatrixValidationResult(ok=False, errors=errors)

    if artifact.get("pack") != "PACK-12":
        errors.append("pack must be PACK-12")
    if artifact.get("artifact") != artifact_name:
        errors.append(f"artifact must be {artifact_name}")

    channels = artifact.get("channels")
    if not isinstance(channels, list):
        errors.append("channels must be a list")
        return SmokeMatrixValidationResult(ok=False, errors=errors)

    channel_by_id: dict[str, dict[str, Any]] = {}
    for index, channel in enumerate(channels):
        if not isinstance(channel, dict):
            errors.append(f"channels[{index}] must be an object")
            continue

        channel_id = channel.get("id")
        if not isinstance(channel_id, str):
            errors.append(f"channels[{index}].id must be a string")
            continue
        if channel_id in channel_by_id:
            errors.append(f"duplicate channel id: {channel_id}")
        channel_by_id[channel_id] = channel

        expected_source = required_channels.get(channel_id)
        if expected_source is None:
            errors.append(f"unexpected channel id: {channel_id}")
            continue

        install_source = channel.get("install_source")
        normalized_source = _normalize_install_source(install_source)
        if normalized_source != expected_source:
            errors.append(
                f"{channel_id} install_source must be {expected_source}, got {install_source!r}"
            )

        checks = channel.get("checks")
        if not isinstance(checks, dict):
            errors.append(f"{channel_id} checks must be an object")
            continue

        extra_checks = sorted(set(checks) - set(REQUIRED_SMOKE_CHECKS))
        if extra_checks:
            errors.append(f"{channel_id} has unknown checks: {', '.join(extra_checks)}")

        for check in REQUIRED_SMOKE_CHECKS:
            status = checks.get(check)
            if status is None:
                errors.append(f"{channel_id} missing required check: {check}")
                continue
            if status not in VALID_CHECK_STATUSES:
                errors.append(f"{channel_id} {check} has invalid status: {status!r}")

        if channel.get("promotion_ready") is True:
            for check in REQUIRED_SMOKE_CHECKS:
                if checks.get(check) != "pass":
                    errors.append(
                        f"{channel_id} is promotion_ready but {check} is not pass"
                    )
            if channel.get("proof_scope") != "actual_host_smoke":
                errors.append(
                    f"{channel_id} is promotion_ready but proof_scope is not actual_host_smoke"
                )
            evidence_artifact = channel.get("smoke_evidence_artifact")
            if not isinstance(evidence_artifact, str) or not evidence_artifact.strip():
                errors.append(
                    f"{channel_id} is promotion_ready but smoke_evidence_artifact is missing"
                )

    for channel_id in required_channels:
        if channel_id not in channel_by_id:
            errors.append(f"missing required channel: {channel_id}")

    if artifact.get("promotion_ready") is True:
        for channel_id, channel in channel_by_id.items():
            if channel.get("promotion_ready") is not True:
                errors.append(f"matrix is promotion_ready but {channel_id} is not")

    return SmokeMatrixValidationResult(ok=not errors, errors=errors)


def validate_smoke_matrix(path: Path) -> SmokeMatrixValidationResult:
    return _validate_smoke_matrix(
        path,
        artifact_name="first-wave-channel-smoke-matrix",
        required_channels=REQUIRED_CHANNELS,
    )


def validate_remaining_smoke_matrix(path: Path) -> SmokeMatrixValidationResult:
    return _validate_smoke_matrix(
        path,
        artifact_name="remaining-channel-smoke-matrix",
        required_channels=REMAINING_REQUIRED_CHANNELS,
    )


def main() -> int:
    default_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-first-wave-smoke-matrix-2026-06-17.json"
    )
    remaining_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-remaining-channel-smoke-matrix-2026-06-17.json"
    )
    first_wave_result = validate_smoke_matrix(default_path)
    remaining_result = validate_remaining_smoke_matrix(remaining_path)
    errors = [
        *(f"first-wave: {error}" for error in first_wave_result.errors),
        *(f"remaining: {error}" for error in remaining_result.errors),
    ]
    result = SmokeMatrixValidationResult(ok=not errors, errors=errors)
    if result.ok:
        print("PACK-12 smoke matrices: ok")
        return 0
    for error in result.errors:
        print(f"error: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
