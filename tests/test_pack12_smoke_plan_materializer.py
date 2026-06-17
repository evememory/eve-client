from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.materialize_pack12_channel_smoke_plan import (
    SmokePlanMaterializeError,
    materialize_smoke_plan,
)
from scripts.validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS


REPO_ROOT = Path(__file__).resolve().parents[1]


def _python_command(source: str) -> list[str]:
    return [sys.executable, "-c", source]


def _commands_payload() -> dict[str, object]:
    return {
        "target": "https://evemem.com",
        "clean_environment": "pytest-clean-pack12-profile",
        "steps": {
            check: {"command": _python_command(f"print('{check} ok')")}
            for check in REQUIRED_SMOKE_CHECKS
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_materializer_writes_concrete_channel_smoke_plan_from_template(
    tmp_path: Path,
) -> None:
    template_path = (
        REPO_ROOT
        / "smoke-plans"
        / "pack12"
        / "claude-code-plugin.actual-host-template.json"
    )
    commands_path = _write_json(tmp_path / "commands.json", _commands_payload())
    output_path = tmp_path / "claude-code-plan.json"

    result = materialize_smoke_plan(template_path, commands_path, output_path)

    assert result.ok
    plan = json.loads(output_path.read_text(encoding="utf-8"))
    assert plan["pack"] == "PACK-12"
    assert plan["artifact"] == "channel-smoke-plan"
    assert plan["channel"] == "claude-code-plugin"
    assert plan["install_source"] == "claude-code-plugin"
    assert plan["proof_scope"] == "actual_host_smoke"
    assert plan["target"] == "https://evemem.com"
    assert plan["clean_environment"] == "pytest-clean-pack12-profile"
    assert set(plan["steps"]) == set(REQUIRED_SMOKE_CHECKS)
    assert "promotion_ready" not in plan
    assert "command_template" not in json.dumps(plan["steps"])
    for check in REQUIRED_SMOKE_CHECKS:
        assert plan["steps"][check]["command"] == _python_command(f"print('{check} ok')")
        assert plan["steps"][check]["must_contain"]
        assert plan["steps"][check]["timeout_seconds"] > 0
        assert plan["steps"][check]["expected_exit_code"] == 0


def test_materializer_requires_command_for_every_smoke_check(tmp_path: Path) -> None:
    template_path = (
        REPO_ROOT
        / "smoke-plans"
        / "pack12"
        / "claude-desktop.actual-host-template.json"
    )
    commands = _commands_payload()
    steps = dict(commands["steps"])  # type: ignore[arg-type]
    steps.pop("forget")
    commands["steps"] = steps
    commands_path = _write_json(tmp_path / "commands.json", commands)

    with pytest.raises(SmokePlanMaterializeError) as exc_info:
        materialize_smoke_plan(template_path, commands_path, tmp_path / "plan.json")

    assert "missing command for required smoke check: forget" in str(exc_info.value)
    assert not (tmp_path / "plan.json").exists()


def test_materializer_rejects_secret_like_command_args(tmp_path: Path) -> None:
    template_path = (
        REPO_ROOT
        / "smoke-plans"
        / "pack12"
        / "codex-plugin.actual-host-template.json"
    )
    commands = _commands_payload()
    steps = dict(commands["steps"])  # type: ignore[arg-type]
    steps["connect"] = {
        "command": ["curl", "-H", "Authorization: Bearer secret-token", "https://evemem.com"]
    }
    commands["steps"] = steps
    commands_path = _write_json(tmp_path / "commands.json", commands)

    with pytest.raises(SmokePlanMaterializeError) as exc_info:
        materialize_smoke_plan(template_path, commands_path, tmp_path / "plan.json")

    assert "connect command contains secret-like content" in str(exc_info.value)
    assert not (tmp_path / "plan.json").exists()


def test_materializer_can_run_as_direct_script() -> None:
    python3 = shutil.which("python3")
    if python3 is None:
        pytest.skip("python3 executable is not available")
    script_path = (
        REPO_ROOT
        / "scripts"
        / "materialize_pack12_channel_smoke_plan.py"
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
