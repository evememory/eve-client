from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from scripts.validate_pack12_smoke_matrix import REQUIRED_CHANNELS, REQUIRED_SMOKE_CHECKS


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_pack12_channel_smoke_gate.py"


def _load_orchestrator() -> ModuleType:
    assert SCRIPT_PATH.exists(), f"missing Pack 12 smoke gate orchestrator: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location("run_pack12_channel_smoke_gate", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _python_command(source: str) -> list[str]:
    return [sys.executable, "-c", source]


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _template_payload() -> dict[str, object]:
    return {
        "pack": "PACK-12",
        "artifact": "channel-smoke-plan-template",
        "schema_version": 1,
        "channel": "claude-code-plugin",
        "install_source": "claude-code-plugin",
        "proof_scope": "actual_host_smoke",
        "promotion_ready": False,
        "operator_required": True,
        "runner": "packages/client/scripts/run_pack12_channel_smoke.py",
        "matrix_artifact": "tmp-matrix.json",
        "evidence_artifact_template": "tmp-evidence.json",
        "not_promoted": ["template only"],
        "steps": {
            check: {
                "purpose": f"prove {check}",
                "command_template": ["operator supplies command"],
                "required_env": [],
                "must_contain": [f"{check} ok"],
                "timeout_seconds": 5,
            }
            for check in REQUIRED_SMOKE_CHECKS
        },
    }


def _commands_payload(*, failing_check: str | None = None) -> dict[str, object]:
    steps: dict[str, object] = {}
    for check in REQUIRED_SMOKE_CHECKS:
        if check == failing_check:
            steps[check] = {"command": _python_command("raise SystemExit(13)")}
        else:
            steps[check] = {"command": _python_command(f"print('{check} ok')")}
    return {
        "target": "https://evemem.com",
        "clean_environment": "pytest-clean-pack12-profile",
        "steps": steps,
    }


def _matrix_payload() -> dict[str, object]:
    return {
        "pack": "PACK-12",
        "artifact": "first-wave-channel-smoke-matrix",
        "status": "not_promoted_smoke_blocked",
        "promotion_ready": False,
        "channels": [
            {
                "id": channel_id,
                "install_source": install_source,
                "promotion_ready": False,
                "checks": {check: "not_run" for check in REQUIRED_SMOKE_CHECKS},
            }
            for channel_id, install_source in REQUIRED_CHANNELS.items()
        ],
    }


def test_smoke_gate_materializes_runs_and_applies_actual_host_evidence(
    tmp_path: Path,
) -> None:
    orchestrator = _load_orchestrator()
    template_path = _write_json(tmp_path / "template.json", _template_payload())
    commands_path = _write_json(tmp_path / "commands.json", _commands_payload())
    matrix_path = _write_json(tmp_path / "matrix.json", _matrix_payload())
    plan_path = tmp_path / "plan.json"
    evidence_path = tmp_path / "evidence.json"
    summary_path = tmp_path / "summary.json"

    result = orchestrator.run_channel_smoke_gate(
        template_path,
        commands_path,
        matrix_path,
        plan_path,
        evidence_path,
        summary_path=summary_path,
    )

    assert result.ok
    assert result.matrix_updated
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["artifact"] == "channel-smoke-gate-run"
    assert summary["status"] == "matrix_updated"
    assert summary["channel"] == "claude-code-plugin"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["proof_scope"] == "actual_host_smoke"
    assert evidence["promotion_ready"] is True
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    channels = {channel["id"]: channel for channel in matrix["channels"]}
    assert channels["claude-code-plugin"]["promotion_ready"] is True
    assert channels["claude-code-plugin"]["checks"] == {
        check: "pass" for check in REQUIRED_SMOKE_CHECKS
    }
    assert channels["claude-desktop"]["promotion_ready"] is False


def test_smoke_gate_does_not_update_matrix_when_runner_fails(tmp_path: Path) -> None:
    orchestrator = _load_orchestrator()
    template_path = _write_json(tmp_path / "template.json", _template_payload())
    commands_path = _write_json(
        tmp_path / "commands.json",
        _commands_payload(failing_check="read"),
    )
    matrix_path = _write_json(tmp_path / "matrix.json", _matrix_payload())
    original_matrix = matrix_path.read_text(encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    evidence_path = tmp_path / "evidence.json"
    summary_path = tmp_path / "summary.json"

    result = orchestrator.run_channel_smoke_gate(
        template_path,
        commands_path,
        matrix_path,
        plan_path,
        evidence_path,
        summary_path=summary_path,
    )

    assert not result.ok
    assert not result.matrix_updated
    assert result.failed_check == "read"
    assert matrix_path.read_text(encoding="utf-8") == original_matrix
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "smoke_failed"
    assert summary["matrix_updated"] is False


def test_smoke_gate_can_run_as_direct_script() -> None:
    _load_orchestrator()
    python3 = shutil.which("python3")
    assert python3 is not None
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [python3, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert completed.returncode == 0
    assert "channel-smoke-gate" in completed.stdout
