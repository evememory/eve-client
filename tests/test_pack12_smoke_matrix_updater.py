from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.apply_pack12_channel_smoke_evidence import (
    SmokeEvidenceError,
    apply_channel_smoke_evidence,
)
from scripts.validate_pack12_smoke_matrix import REQUIRED_CHANNELS, REQUIRED_SMOKE_CHECKS


def _matrix() -> dict[str, object]:
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


def _actual_host_evidence(channel: str = "claude-code-plugin") -> dict[str, object]:
    return {
        "pack": "PACK-12",
        "artifact": "channel-smoke-evidence",
        "channel": channel,
        "install_source": REQUIRED_CHANNELS[channel],
        "proof_scope": "actual_host_smoke",
        "promotion_ready": True,
        "checks": {check: "pass" for check in REQUIRED_SMOKE_CHECKS},
        "step_results": [
            {"check": check, "status": "pass"} for check in REQUIRED_SMOKE_CHECKS
        ],
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_smoke_matrix_updater_rejects_local_dry_run_evidence(tmp_path: Path) -> None:
    matrix_path = tmp_path / "matrix.json"
    evidence_path = tmp_path / "evidence.json"
    evidence = _actual_host_evidence()
    evidence["proof_scope"] = "local_dry_run"
    evidence["promotion_ready"] = False
    _write_json(matrix_path, _matrix())
    _write_json(evidence_path, evidence)

    with pytest.raises(SmokeEvidenceError) as exc_info:
        apply_channel_smoke_evidence(matrix_path, evidence_path)

    assert "actual_host_smoke proof_scope is required" in str(exc_info.value)


def test_smoke_matrix_updater_promotes_only_evidence_channel(tmp_path: Path) -> None:
    matrix_path = tmp_path / "matrix.json"
    evidence_path = tmp_path / "evidence.json"
    _write_json(matrix_path, _matrix())
    _write_json(evidence_path, _actual_host_evidence())

    result = apply_channel_smoke_evidence(matrix_path, evidence_path)

    assert result.ok
    updated = json.loads(matrix_path.read_text(encoding="utf-8"))
    channels = {channel["id"]: channel for channel in updated["channels"]}
    promoted = channels["claude-code-plugin"]
    assert promoted["promotion_ready"] is True
    assert promoted["checks"] == {check: "pass" for check in REQUIRED_SMOKE_CHECKS}
    assert promoted["proof_scope"] == "actual_host_smoke"
    assert promoted["smoke_evidence_artifact"] == str(evidence_path)
    assert channels["claude-desktop"]["promotion_ready"] is False
    assert updated["promotion_ready"] is False


def test_smoke_matrix_updater_rejects_incomplete_actual_host_evidence(
    tmp_path: Path,
) -> None:
    matrix_path = tmp_path / "matrix.json"
    evidence_path = tmp_path / "evidence.json"
    evidence = _actual_host_evidence()
    evidence["checks"] = copy.deepcopy(evidence["checks"])
    evidence["checks"]["read"] = "fail"  # type: ignore[index]
    evidence["promotion_ready"] = False
    _write_json(matrix_path, _matrix())
    _write_json(evidence_path, evidence)

    with pytest.raises(SmokeEvidenceError) as exc_info:
        apply_channel_smoke_evidence(matrix_path, evidence_path)

    assert "read must be pass" in str(exc_info.value)


def test_smoke_matrix_updater_rejects_channel_source_mismatch(tmp_path: Path) -> None:
    matrix_path = tmp_path / "matrix.json"
    evidence_path = tmp_path / "evidence.json"
    evidence = _actual_host_evidence("claude-code-plugin")
    evidence["install_source"] = "codex-plugin"
    _write_json(matrix_path, _matrix())
    _write_json(evidence_path, evidence)

    with pytest.raises(SmokeEvidenceError) as exc_info:
        apply_channel_smoke_evidence(matrix_path, evidence_path)

    assert "install_source must be claude-code-plugin" in str(exc_info.value)


def test_smoke_matrix_updater_can_run_as_direct_script() -> None:
    python3 = shutil.which("python3")
    if python3 is None:
        pytest.skip("python3 executable is not available")
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "apply_pack12_channel_smoke_evidence.py"
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
    assert "channel-smoke-evidence" in completed.stdout
