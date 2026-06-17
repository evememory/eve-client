from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.validate_pack12_smoke_matrix import (
        REMAINING_REQUIRED_CHANNELS,
        REQUIRED_CHANNELS,
        REQUIRED_SMOKE_CHECKS,
        validate_remaining_smoke_matrix,
        validate_smoke_matrix,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_pack12_smoke_matrix import (  # type: ignore[no-redef]
        REMAINING_REQUIRED_CHANNELS,
        REQUIRED_CHANNELS,
        REQUIRED_SMOKE_CHECKS,
        validate_remaining_smoke_matrix,
        validate_smoke_matrix,
    )


ALL_REQUIRED_CHANNELS = REQUIRED_CHANNELS | REMAINING_REQUIRED_CHANNELS


class SmokeEvidenceError(ValueError):
    """Raised when channel smoke evidence is not promotion-safe."""


@dataclass(frozen=True)
class MatrixUpdateResult:
    ok: bool
    matrix_path: Path
    channel: str
    matrix_promotion_ready: bool


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeEvidenceError(f"missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeEvidenceError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokeEvidenceError(f"{label} must be a JSON object")
    return payload


def _validate_evidence(evidence: dict[str, Any]) -> tuple[str, str]:
    if evidence.get("pack") != "PACK-12":
        raise SmokeEvidenceError("evidence pack must be PACK-12")
    if evidence.get("artifact") != "channel-smoke-evidence":
        raise SmokeEvidenceError("evidence artifact must be channel-smoke-evidence")

    channel = evidence.get("channel")
    if not isinstance(channel, str) or channel not in ALL_REQUIRED_CHANNELS:
        raise SmokeEvidenceError(f"unsupported evidence channel: {channel!r}")

    expected_source = ALL_REQUIRED_CHANNELS[channel]
    install_source = evidence.get("install_source")
    if install_source != expected_source:
        raise SmokeEvidenceError(
            f"{channel} install_source must be {expected_source}, got {install_source!r}"
        )

    if evidence.get("proof_scope") != "actual_host_smoke":
        raise SmokeEvidenceError("actual_host_smoke proof_scope is required")

    checks = evidence.get("checks")
    if not isinstance(checks, dict):
        raise SmokeEvidenceError("evidence checks must be an object")
    for check in REQUIRED_SMOKE_CHECKS:
        if checks.get(check) != "pass":
            raise SmokeEvidenceError(f"{check} must be pass")
    if evidence.get("promotion_ready") is not True:
        raise SmokeEvidenceError("evidence promotion_ready must be true")

    return channel, expected_source


def _validate_matrix_shape(matrix: dict[str, Any]) -> None:
    if matrix.get("pack") != "PACK-12":
        raise SmokeEvidenceError("matrix pack must be PACK-12")
    if matrix.get("artifact") not in {
        "first-wave-channel-smoke-matrix",
        "remaining-channel-smoke-matrix",
    }:
        raise SmokeEvidenceError("matrix artifact is not a PACK-12 smoke matrix")
    channels = matrix.get("channels")
    if not isinstance(channels, list):
        raise SmokeEvidenceError("matrix channels must be a list")


def _matrix_validator(matrix: dict[str, Any], matrix_path: Path) -> None:
    artifact = matrix.get("artifact")
    if artifact == "first-wave-channel-smoke-matrix":
        result = validate_smoke_matrix(matrix_path)
    else:
        result = validate_remaining_smoke_matrix(matrix_path)
    if not result.ok:
        raise SmokeEvidenceError("; ".join(result.errors))


def _find_channel(matrix: dict[str, Any], channel_id: str) -> dict[str, Any]:
    for channel in matrix["channels"]:
        if isinstance(channel, dict) and channel.get("id") == channel_id:
            return channel
    raise SmokeEvidenceError(f"matrix does not contain channel: {channel_id}")


def apply_channel_smoke_evidence(
    matrix_path: Path,
    evidence_path: Path,
) -> MatrixUpdateResult:
    matrix = _load_json_object(matrix_path, label="smoke matrix")
    evidence = _load_json_object(evidence_path, label="channel smoke evidence")
    _validate_matrix_shape(matrix)
    channel_id, expected_source = _validate_evidence(evidence)

    channel = _find_channel(matrix, channel_id)
    if channel.get("install_source") != expected_source:
        raise SmokeEvidenceError(
            f"matrix {channel_id} install_source must be {expected_source}"
        )

    channel["checks"] = {check: "pass" for check in REQUIRED_SMOKE_CHECKS}
    channel["promotion_ready"] = True
    channel["proof_scope"] = "actual_host_smoke"
    channel["smoke_evidence_artifact"] = str(evidence_path)
    channel["smoke_evidence_applied_at"] = _utc_now()

    matrix["promotion_ready"] = all(
        isinstance(item, dict) and item.get("promotion_ready") is True
        for item in matrix["channels"]
    )
    matrix["status"] = (
        "promotion_ready"
        if matrix["promotion_ready"] is True
        else "partial_smoke_evidence_applied"
    )
    matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    _matrix_validator(matrix, matrix_path)
    return MatrixUpdateResult(
        ok=True,
        matrix_path=matrix_path,
        channel=channel_id,
        matrix_promotion_ready=bool(matrix["promotion_ready"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply actual PACK-12 channel smoke evidence to a smoke matrix."
    )
    parser.add_argument("matrix", type=Path, help="Path to PACK-12 smoke matrix JSON")
    parser.add_argument(
        "evidence", type=Path, help="Path to channel-smoke-evidence JSON"
    )
    args = parser.parse_args()
    try:
        result = apply_channel_smoke_evidence(args.matrix, args.evidence)
    except SmokeEvidenceError as exc:
        print(f"error: {exc}")
        return 2
    print(
        f"applied {result.channel} evidence to {result.matrix_path}; "
        f"matrix_promotion_ready={str(result.matrix_promotion_ready).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
