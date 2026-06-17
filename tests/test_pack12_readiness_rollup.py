from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = REPO_ROOT.parents[1]
MONOREPO_ARTIFACTS_ROOT = MONOREPO_ROOT / "docs" / "specs" / "artifacts"
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_pack12_readiness_rollup.py"

if not MONOREPO_ARTIFACTS_ROOT.exists():
    pytest.skip(
        "monorepo Pack 12 evidence artifacts are not available",
        allow_module_level=True,
    )


def _load_verifier() -> ModuleType:
    assert SCRIPT_PATH.exists(), f"missing Pack 12 readiness rollup verifier: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location(
        "validate_pack12_readiness_rollup",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pack12_readiness_rollup_passes_for_current_artifacts() -> None:
    verifier = _load_verifier()

    result = verifier.validate_pack12_readiness_rollup(REPO_ROOT, MONOREPO_ROOT)

    assert result.ok
    assert result.errors == []


def test_pack12_readiness_rollup_rejects_promoted_readiness_artifact(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    docs_root = tmp_path / "docs" / "specs" / "artifacts"
    docs_root.mkdir(parents=True)
    artifact_path = docs_root / "pack12-smoke-gate-orchestrator-readiness-2026-06-17.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pack": "PACK-12",
                "artifact": "smoke-gate-orchestrator-readiness",
                "promotion_ready": True,
            }
        ),
        encoding="utf-8",
    )

    errors = verifier._validate_readiness_artifact(
        tmp_path,
        "docs/specs/artifacts/pack12-smoke-gate-orchestrator-readiness-2026-06-17.json",
    )

    assert errors == [
        "docs/specs/artifacts/pack12-smoke-gate-orchestrator-readiness-2026-06-17.json promotion_ready must be false"
    ]


def test_pack12_readiness_rollup_can_run_as_direct_script() -> None:
    _load_verifier()
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
    assert "PACK-12 readiness rollup" in completed.stdout
