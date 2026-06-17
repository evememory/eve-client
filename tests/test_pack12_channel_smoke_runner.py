from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_pack12_channel_smoke import (
    SmokePlanError,
    run_channel_smoke_plan,
)
from scripts.validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS


def _python_command(source: str) -> list[str]:
    return [sys.executable, "-c", source]


def _base_plan(tmp_path: Path, *, proof_scope: str = "local_dry_run") -> dict[str, object]:
    return {
        "pack": "PACK-12",
        "artifact": "channel-smoke-plan",
        "channel": "claude-code-plugin",
        "install_source": "claude-code-plugin",
        "target": "https://evemem.com",
        "proof_scope": proof_scope,
        "clean_environment": "pytest-clean-profile",
        "steps": {
            check: {"command": _python_command(f"print('{check} ok')")}
            for check in REQUIRED_SMOKE_CHECKS
        },
    }


def _write_plan(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_pack12_channel_smoke_plan_requires_every_required_check(tmp_path: Path) -> None:
    plan = _base_plan(tmp_path)
    steps = dict(plan["steps"])  # type: ignore[arg-type]
    steps.pop("forget")
    plan["steps"] = steps

    with pytest.raises(SmokePlanError) as exc_info:
        run_channel_smoke_plan(
            _write_plan(tmp_path, plan),
            tmp_path / "evidence.json",
        )

    assert "missing required smoke check: forget" in str(exc_info.value)


def test_pack12_channel_smoke_runner_writes_resumable_local_evidence(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"

    result = run_channel_smoke_plan(
        _write_plan(tmp_path, _base_plan(tmp_path)),
        evidence_path,
    )

    assert result.ok
    artifact = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "channel-smoke-evidence"
    assert artifact["channel"] == "claude-code-plugin"
    assert artifact["install_source"] == "claude-code-plugin"
    assert artifact["proof_scope"] == "local_dry_run"
    assert artifact["checks"] == {check: "pass" for check in REQUIRED_SMOKE_CHECKS}
    assert artifact["promotion_ready"] is False
    assert "actual_host_smoke proof_scope is required for promotion" in artifact["not_promoted"]
    assert artifact["resume_supported"] is True


def test_pack12_channel_smoke_runner_redacts_output_and_stops_on_failure(
    tmp_path: Path,
) -> None:
    plan = _base_plan(tmp_path)
    steps = dict(plan["steps"])  # type: ignore[arg-type]
    steps["clean_environment"] = {
        "command": _python_command("print('Bearer secret-token-123')")
    }
    steps["entry_url"] = {"command": _python_command("raise SystemExit(7)")}
    plan["steps"] = steps
    evidence_path = tmp_path / "evidence.json"

    result = run_channel_smoke_plan(
        _write_plan(tmp_path, plan),
        evidence_path,
    )

    assert not result.ok
    artifact = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert artifact["checks"]["clean_environment"] == "pass"
    assert artifact["checks"]["entry_url"] == "fail"
    assert artifact["checks"]["install_or_import"] == "not_run"
    first_step = artifact["step_results"][0]
    assert "secret-token-123" not in json.dumps(first_step)
    assert "Bearer [REDACTED]" in first_step["stdout_preview"]
    assert artifact["promotion_ready"] is False


def test_pack12_channel_smoke_runner_resume_skips_previously_passed_steps(
    tmp_path: Path,
) -> None:
    plan = _base_plan(tmp_path, proof_scope="actual_host_smoke")
    steps = dict(plan["steps"])  # type: ignore[arg-type]
    steps["entry_url"] = {"command": _python_command("raise SystemExit(9)")}
    plan["steps"] = steps
    plan_path = _write_plan(tmp_path, plan)
    evidence_path = tmp_path / "evidence.json"

    first_result = run_channel_smoke_plan(plan_path, evidence_path)
    assert not first_result.ok

    steps["entry_url"] = {"command": _python_command("print('entry_url repaired')")}
    plan["steps"] = steps
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    resumed_result = run_channel_smoke_plan(plan_path, evidence_path, resume=True)

    assert resumed_result.ok
    artifact = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert artifact["promotion_ready"] is True
    assert artifact["step_results"][0]["resumed"] is True
    assert artifact["checks"] == {check: "pass" for check in REQUIRED_SMOKE_CHECKS}


def test_pack12_channel_smoke_runner_can_run_as_direct_script() -> None:
    python3 = shutil.which("python3")
    if python3 is None:
        pytest.skip("python3 executable is not available")
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_pack12_channel_smoke.py"
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [python3, str(script_path), "--help"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert completed.returncode == 0
    assert "channel-smoke-plan" in completed.stdout
