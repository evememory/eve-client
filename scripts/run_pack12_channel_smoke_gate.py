from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.apply_pack12_channel_smoke_evidence import (
        MatrixUpdateResult,
        SmokeEvidenceError,
        apply_channel_smoke_evidence,
    )
    from scripts.materialize_pack12_channel_smoke_plan import (
        SmokePlanMaterializeError,
        materialize_smoke_plan,
    )
    from scripts.run_pack12_channel_smoke import (
        ChannelSmokeRunResult,
        SmokePlanError,
        run_channel_smoke_plan,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apply_pack12_channel_smoke_evidence import (  # type: ignore[no-redef]
        MatrixUpdateResult,
        SmokeEvidenceError,
        apply_channel_smoke_evidence,
    )
    from materialize_pack12_channel_smoke_plan import (  # type: ignore[no-redef]
        SmokePlanMaterializeError,
        materialize_smoke_plan,
    )
    from run_pack12_channel_smoke import (  # type: ignore[no-redef]
        ChannelSmokeRunResult,
        SmokePlanError,
        run_channel_smoke_plan,
    )


class SmokeGateError(ValueError):
    """Raised when a PACK-12 smoke gate cannot run safely."""


@dataclass(frozen=True)
class ChannelSmokeGateResult:
    ok: bool
    status: str
    plan_path: Path
    evidence_path: Path
    matrix_path: Path
    summary_path: Path | None = None
    channel: str | None = None
    failed_check: str | None = None
    matrix_updated: bool = False
    matrix_promotion_ready: bool = False
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_channel(plan_path: Path) -> str | None:
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    channel = payload.get("channel")
    return channel if isinstance(channel, str) else None


def _write_summary(
    summary_path: Path | None,
    *,
    status: str,
    template_path: Path,
    commands_path: Path,
    matrix_path: Path,
    plan_path: Path,
    evidence_path: Path,
    channel: str | None,
    smoke_result: ChannelSmokeRunResult | None,
    matrix_result: MatrixUpdateResult | None,
    error: str | None = None,
) -> None:
    if summary_path is None:
        return
    payload: dict[str, Any] = {
        "pack": "PACK-12",
        "artifact": "channel-smoke-gate-run",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "status": status,
        "channel": channel,
        "template_artifact": str(template_path),
        "commands_artifact": str(commands_path),
        "plan_artifact": str(plan_path),
        "evidence_artifact": str(evidence_path),
        "matrix_artifact": str(matrix_path),
        "smoke_ok": bool(smoke_result and smoke_result.ok),
        "failed_check": smoke_result.failed_check if smoke_result else None,
        "matrix_updated": matrix_result is not None,
        "matrix_promotion_ready": bool(
            matrix_result and matrix_result.matrix_promotion_ready
        ),
        "error": error,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_channel_smoke_gate(
    template_path: Path,
    commands_path: Path,
    matrix_path: Path,
    plan_output_path: Path,
    evidence_output_path: Path,
    *,
    summary_path: Path | None = None,
    resume: bool = False,
    continue_on_failure: bool = False,
) -> ChannelSmokeGateResult:
    try:
        materialize_smoke_plan(template_path, commands_path, plan_output_path)
    except SmokePlanMaterializeError as exc:
        error = str(exc)
        _write_summary(
            summary_path,
            status="materialize_failed",
            template_path=template_path,
            commands_path=commands_path,
            matrix_path=matrix_path,
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            channel=None,
            smoke_result=None,
            matrix_result=None,
            error=error,
        )
        return ChannelSmokeGateResult(
            ok=False,
            status="materialize_failed",
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            matrix_path=matrix_path,
            summary_path=summary_path,
            error=error,
        )

    channel = _load_channel(plan_output_path)
    try:
        smoke_result = run_channel_smoke_plan(
            plan_output_path,
            evidence_output_path,
            resume=resume,
            continue_on_failure=continue_on_failure,
        )
    except SmokePlanError as exc:
        error = str(exc)
        _write_summary(
            summary_path,
            status="smoke_plan_rejected",
            template_path=template_path,
            commands_path=commands_path,
            matrix_path=matrix_path,
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            channel=channel,
            smoke_result=None,
            matrix_result=None,
            error=error,
        )
        return ChannelSmokeGateResult(
            ok=False,
            status="smoke_plan_rejected",
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            matrix_path=matrix_path,
            summary_path=summary_path,
            channel=channel,
            error=error,
        )

    if not smoke_result.ok:
        _write_summary(
            summary_path,
            status="smoke_failed",
            template_path=template_path,
            commands_path=commands_path,
            matrix_path=matrix_path,
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            channel=channel,
            smoke_result=smoke_result,
            matrix_result=None,
        )
        return ChannelSmokeGateResult(
            ok=False,
            status="smoke_failed",
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            matrix_path=matrix_path,
            summary_path=summary_path,
            channel=channel,
            failed_check=smoke_result.failed_check,
        )

    try:
        matrix_result = apply_channel_smoke_evidence(matrix_path, evidence_output_path)
    except SmokeEvidenceError as exc:
        error = str(exc)
        _write_summary(
            summary_path,
            status="matrix_update_rejected",
            template_path=template_path,
            commands_path=commands_path,
            matrix_path=matrix_path,
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            channel=channel,
            smoke_result=smoke_result,
            matrix_result=None,
            error=error,
        )
        return ChannelSmokeGateResult(
            ok=False,
            status="matrix_update_rejected",
            plan_path=plan_output_path,
            evidence_path=evidence_output_path,
            matrix_path=matrix_path,
            summary_path=summary_path,
            channel=channel,
            error=error,
        )

    _write_summary(
        summary_path,
        status="matrix_updated",
        template_path=template_path,
        commands_path=commands_path,
        matrix_path=matrix_path,
        plan_path=plan_output_path,
        evidence_path=evidence_output_path,
        channel=channel,
        smoke_result=smoke_result,
        matrix_result=matrix_result,
    )
    return ChannelSmokeGateResult(
        ok=True,
        status="matrix_updated",
        plan_path=plan_output_path,
        evidence_path=evidence_output_path,
        matrix_path=matrix_path,
        summary_path=summary_path,
        channel=channel,
        matrix_updated=True,
        matrix_promotion_ready=matrix_result.matrix_promotion_ready,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a PACK-12 channel-smoke-gate: materialize, smoke, then apply evidence."
    )
    parser.add_argument("template", type=Path, help="Path to channel-smoke-plan-template JSON")
    parser.add_argument("commands", type=Path, help="Path to JSON with concrete commands")
    parser.add_argument("matrix", type=Path, help="Path to PACK-12 smoke matrix JSON")
    parser.add_argument("plan_output", type=Path, help="Path to write materialized plan")
    parser.add_argument("evidence_output", type=Path, help="Path to write smoke evidence")
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional path to write channel-smoke-gate-run summary JSON",
    )
    parser.add_argument("--resume", action="store_true", help="Resume passed smoke checks")
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Run later smoke checks even after a failed check",
    )
    args = parser.parse_args()
    result = run_channel_smoke_gate(
        args.template,
        args.commands,
        args.matrix,
        args.plan_output,
        args.evidence_output,
        summary_path=args.summary_output,
        resume=args.resume,
        continue_on_failure=args.continue_on_failure,
    )
    print(
        f"channel-smoke-gate status={result.status} "
        f"matrix_updated={str(result.matrix_updated).lower()} "
        f"summary={result.summary_path or 'none'}"
    )
    if result.ok:
        return 0
    return 1 if result.status == "smoke_failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
