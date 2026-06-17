from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_REMOTE_CHANNELS = {
    "claude-desktop": "claude-desktop",
    "chatgpt-app": "chatgpt-app",
}

REQUIRED_REMOTE_LOCAL_CHECKS = (
    "protected_route_preserves_return_to_query",
    "login_url_forwards_install_source",
    "login_url_preserves_tool_query",
    "invalid_install_source_not_forwarded",
)

VALID_STATUSES = {"pass", "fail", "not_run", "blocked"}


@dataclass(frozen=True)
class RemoteEntryPointSmokeValidationResult:
    ok: bool
    errors: list[str]


def _load_json(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"missing remote entrypoint smoke artifact: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]

    if not isinstance(payload, dict):
        return None, ["remote entrypoint smoke artifact must be a JSON object"]
    return payload, []


def validate_remote_entrypoint_smoke(path: Path) -> RemoteEntryPointSmokeValidationResult:
    artifact, errors = _load_json(path)
    if artifact is None:
        return RemoteEntryPointSmokeValidationResult(ok=False, errors=errors)

    if artifact.get("pack") != "PACK-12":
        errors.append("pack must be PACK-12")
    if artifact.get("artifact") != "remote-entrypoint-local-smoke":
        errors.append("artifact must be remote-entrypoint-local-smoke")
    if artifact.get("promotion_ready") is True:
        errors.append("local-only remote entrypoint smoke cannot set promotion_ready=true")
    if artifact.get("production_status") != "blocked":
        errors.append("production_status must remain blocked until hosted redirect is verified")

    channels = artifact.get("channels")
    if not isinstance(channels, list):
        errors.append("channels must be a list")
        return RemoteEntryPointSmokeValidationResult(ok=False, errors=errors)

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

        expected_source = REQUIRED_REMOTE_CHANNELS.get(channel_id)
        if expected_source is None:
            errors.append(f"unexpected remote channel id: {channel_id}")
            continue
        if channel.get("install_source") != expected_source:
            errors.append(
                f"{channel_id} install_source must be {expected_source}, got {channel.get('install_source')!r}"
            )
        if channel.get("promotion_ready") is True:
            errors.append(f"{channel_id} cannot be promotion_ready from local-only evidence")

        local_checks = channel.get("local_checks")
        if not isinstance(local_checks, dict):
            errors.append(f"{channel_id} local_checks must be an object")
            continue
        extra_checks = sorted(set(local_checks) - set(REQUIRED_REMOTE_LOCAL_CHECKS))
        if extra_checks:
            errors.append(f"{channel_id} has unknown checks: {', '.join(extra_checks)}")
        for check in REQUIRED_REMOTE_LOCAL_CHECKS:
            status = local_checks.get(check)
            if status is None:
                errors.append(f"{channel_id} missing local check: {check}")
                continue
            if status not in VALID_STATUSES:
                errors.append(f"{channel_id} {check} has invalid status: {status!r}")
            elif status != "pass":
                errors.append(f"{channel_id} {check} must be pass for local smoke")

    for channel_id in REQUIRED_REMOTE_CHANNELS:
        if channel_id not in channel_by_id:
            errors.append(f"missing remote channel: {channel_id}")

    return RemoteEntryPointSmokeValidationResult(ok=not errors, errors=errors)


def main() -> int:
    default_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-remote-entrypoint-local-smoke-2026-06-17.json"
    )
    result = validate_remote_entrypoint_smoke(default_path)
    if result.ok:
        print("PACK-12 remote entrypoint local smoke: ok")
        return 0
    for error in result.errors:
        print(f"error: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
