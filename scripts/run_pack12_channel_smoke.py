from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.validate_pack12_smoke_matrix import (
        REMAINING_REQUIRED_CHANNELS,
        REQUIRED_CHANNELS,
        REQUIRED_SMOKE_CHECKS,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_pack12_smoke_matrix import (  # type: ignore[no-redef]
        REMAINING_REQUIRED_CHANNELS,
        REQUIRED_CHANNELS,
        REQUIRED_SMOKE_CHECKS,
    )


ALL_REQUIRED_CHANNELS = REQUIRED_CHANNELS | REMAINING_REQUIRED_CHANNELS
VALID_PROOF_SCOPES = {"actual_host_smoke", "local_dry_run"}
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_PREVIEW_CHARS = 2000

_BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|authorization)\b\s*[:=]\s*['\"]?[^'\"\s]+"
)


class SmokePlanError(ValueError):
    """Raised when a PACK-12 channel smoke plan is invalid."""


@dataclass(frozen=True)
class ChannelSmokeRunResult:
    ok: bool
    artifact_path: Path
    failed_check: str | None = None


@dataclass(frozen=True)
class _SmokePlan:
    channel: str
    install_source: str
    target: str
    proof_scope: str
    clean_environment: str
    steps: dict[str, dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokePlanError(f"missing smoke plan: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokePlanError(f"invalid JSON smoke plan: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokePlanError("smoke plan must be a JSON object")
    return payload


def _as_non_empty_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SmokePlanError(f"{key} must be a non-empty string")
    return value.strip()


def _validate_command(check: str, raw_step: object) -> dict[str, Any]:
    if not isinstance(raw_step, dict):
        raise SmokePlanError(f"{check} step must be an object")
    command = raw_step.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise SmokePlanError(f"{check} command must be a non-empty string array")
    timeout = raw_step.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if not isinstance(timeout, int | float) or timeout <= 0:
        raise SmokePlanError(f"{check} timeout_seconds must be positive")
    expected_exit_code = raw_step.get("expected_exit_code", 0)
    if not isinstance(expected_exit_code, int):
        raise SmokePlanError(f"{check} expected_exit_code must be an integer")
    must_contain = raw_step.get("must_contain", [])
    if not isinstance(must_contain, list) or not all(
        isinstance(item, str) and item for item in must_contain
    ):
        raise SmokePlanError(f"{check} must_contain must be a string array")
    return {
        "command": command,
        "timeout_seconds": float(timeout),
        "expected_exit_code": expected_exit_code,
        "must_contain": must_contain,
    }


def _load_plan(plan_path: Path) -> _SmokePlan:
    payload = _load_json_object(plan_path)
    if payload.get("pack") != "PACK-12":
        raise SmokePlanError("pack must be PACK-12")
    if payload.get("artifact") != "channel-smoke-plan":
        raise SmokePlanError("artifact must be channel-smoke-plan")

    channel = _as_non_empty_string(payload, "channel")
    expected_source = ALL_REQUIRED_CHANNELS.get(channel)
    if expected_source is None:
        raise SmokePlanError(f"unsupported PACK-12 channel: {channel}")

    install_source = _as_non_empty_string(payload, "install_source")
    if install_source != expected_source:
        raise SmokePlanError(
            f"{channel} install_source must be {expected_source}, got {install_source}"
        )

    proof_scope = _as_non_empty_string(payload, "proof_scope")
    if proof_scope not in VALID_PROOF_SCOPES:
        raise SmokePlanError(
            f"proof_scope must be one of {sorted(VALID_PROOF_SCOPES)}, got {proof_scope}"
        )

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, dict):
        raise SmokePlanError("steps must be an object")

    steps: dict[str, dict[str, Any]] = {}
    for check in REQUIRED_SMOKE_CHECKS:
        if check not in raw_steps:
            raise SmokePlanError(f"missing required smoke check: {check}")
        steps[check] = _validate_command(check, raw_steps[check])

    extra_checks = sorted(set(raw_steps) - set(REQUIRED_SMOKE_CHECKS))
    if extra_checks:
        raise SmokePlanError(f"unknown smoke checks: {', '.join(extra_checks)}")

    return _SmokePlan(
        channel=channel,
        install_source=install_source,
        target=_as_non_empty_string(payload, "target"),
        proof_scope=proof_scope,
        clean_environment=_as_non_empty_string(payload, "clean_environment"),
        steps=steps,
    )


def _redact(text: str) -> str:
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1=[REDACTED]", redacted)
    if len(redacted) > MAX_PREVIEW_CHARS:
        return redacted[:MAX_PREVIEW_CHARS] + "...[truncated]"
    return redacted


def _redact_command(command: list[str]) -> list[str]:
    return [_redact(part) for part in command]


def _load_previous_passes(output_path: Path) -> dict[str, dict[str, Any]]:
    if not output_path.exists():
        return {}
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    previous_steps = payload.get("step_results")
    if not isinstance(previous_steps, list):
        return {}

    passed: dict[str, dict[str, Any]] = {}
    for step in previous_steps:
        if not isinstance(step, dict):
            continue
        check = step.get("check")
        if isinstance(check, str) and step.get("status") == "pass":
            passed[check] = step
    return passed


def _run_step(check: str, step: dict[str, Any]) -> dict[str, Any]:
    started_at = _utc_now()
    start = time.monotonic()
    command = step["command"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=step["timeout_seconds"],
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        combined_output = stdout + "\n" + stderr
        contains_required = all(fragment in combined_output for fragment in step["must_contain"])
        status = (
            "pass"
            if completed.returncode == step["expected_exit_code"] and contains_required
            else "fail"
        )
        failure_reason = None
        if completed.returncode != step["expected_exit_code"]:
            failure_reason = (
                f"exit_code {completed.returncode} != expected {step['expected_exit_code']}"
            )
        elif not contains_required:
            missing = [
                fragment
                for fragment in step["must_contain"]
                if fragment not in combined_output
            ]
            failure_reason = f"missing required output: {', '.join(missing)}"
        return {
            "check": check,
            "status": status,
            "started_at": started_at,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "command": _redact_command(command),
            "return_code": completed.returncode,
            "stdout_preview": _redact(stdout),
            "stderr_preview": _redact(stderr),
            "failure_reason": failure_reason,
            "resumed": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "check": check,
            "status": "fail",
            "started_at": started_at,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "command": _redact_command(command),
            "return_code": None,
            "stdout_preview": _redact(stdout),
            "stderr_preview": _redact(stderr),
            "failure_reason": f"timeout after {step['timeout_seconds']}s",
            "resumed": False,
        }


def _artifact(
    plan: _SmokePlan,
    *,
    checks: dict[str, str],
    step_results: list[dict[str, Any]],
    failed_check: str | None,
) -> dict[str, Any]:
    all_pass = all(checks[check] == "pass" for check in REQUIRED_SMOKE_CHECKS)
    promotion_ready = all_pass and plan.proof_scope == "actual_host_smoke"
    not_promoted: list[str] = []
    if not promotion_ready:
        if plan.proof_scope != "actual_host_smoke":
            not_promoted.append("actual_host_smoke proof_scope is required for promotion")
        if failed_check:
            not_promoted.append(f"{failed_check} failed")
        for check in REQUIRED_SMOKE_CHECKS:
            if checks[check] == "not_run":
                not_promoted.append(f"{check} was not run")
                break

    return {
        "pack": "PACK-12",
        "artifact": "channel-smoke-evidence",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "channel": plan.channel,
        "install_source": plan.install_source,
        "target": plan.target,
        "proof_scope": plan.proof_scope,
        "clean_environment": plan.clean_environment,
        "required_smoke_checks": list(REQUIRED_SMOKE_CHECKS),
        "checks": checks,
        "step_results": step_results,
        "resume_supported": True,
        "promotion_ready": promotion_ready,
        "not_promoted": not_promoted,
    }


def _write_artifact(output_path: Path, artifact: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")


def run_channel_smoke_plan(
    plan_path: Path,
    output_path: Path,
    *,
    resume: bool = False,
    continue_on_failure: bool = False,
) -> ChannelSmokeRunResult:
    plan = _load_plan(plan_path)
    previous_passes = _load_previous_passes(output_path) if resume else {}
    checks = {check: "not_run" for check in REQUIRED_SMOKE_CHECKS}
    step_results: list[dict[str, Any]] = []
    failed_check: str | None = None

    for check in REQUIRED_SMOKE_CHECKS:
        if check in previous_passes:
            previous = dict(previous_passes[check])
            previous["resumed"] = True
            checks[check] = "pass"
            step_results.append(previous)
            continue

        result = _run_step(check, plan.steps[check])
        checks[check] = result["status"]
        step_results.append(result)
        if result["status"] != "pass" and failed_check is None:
            failed_check = check

        _write_artifact(
            output_path,
            _artifact(
                plan,
                checks=checks,
                step_results=step_results,
                failed_check=failed_check,
            ),
        )

        if failed_check and not continue_on_failure:
            break

    final_artifact = _artifact(
        plan,
        checks=checks,
        step_results=step_results,
        failed_check=failed_check,
    )
    _write_artifact(output_path, final_artifact)
    return ChannelSmokeRunResult(
        ok=failed_check is None,
        artifact_path=output_path,
        failed_check=failed_check,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a resumable PACK-12 channel smoke plan and emit evidence."
    )
    parser.add_argument("plan", type=Path, help="Path to channel-smoke-plan JSON")
    parser.add_argument("output", type=Path, help="Path to write evidence JSON")
    parser.add_argument("--resume", action="store_true", help="Skip checks already passed")
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Run later checks even after a failed check",
    )
    args = parser.parse_args()
    try:
        result = run_channel_smoke_plan(
            args.plan,
            args.output,
            resume=args.resume,
            continue_on_failure=args.continue_on_failure,
        )
    except SmokePlanError as exc:
        print(f"error: {exc}")
        return 2
    print(f"wrote {result.artifact_path}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
