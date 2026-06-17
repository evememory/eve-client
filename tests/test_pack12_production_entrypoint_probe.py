from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


MONOREPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = MONOREPO_ROOT / "scripts" / "deployment" / "verify_pack12_entrypoints.py"

if not SCRIPT_PATH.exists():
    pytest.skip("monorepo Pack 12 entrypoint probe is not available", allow_module_level=True)

spec = importlib.util.spec_from_file_location("verify_pack12_entrypoints", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def test_installer_probe_accepts_source_tagged_installer_body() -> None:
    result = probe.validate_response(
        "claude-code-plugin",
        200,
        {},
        'INSTALL_SOURCE="claude-code-plugin"\n'
        'echo "Do not pipe this installer directly to sh." >&2\n'
        '"$INSTALLED_BINARY" config set-install-source "$INSTALL_SOURCE" >/dev/null\n'
        'echo "  eve connect --install-source \\"$INSTALL_SOURCE\\""\n',
    )

    assert result.ok
    assert result.errors == []


def test_installer_probe_rejects_pre_source_tagged_installer_body() -> None:
    result = probe.validate_response(
        "claude-code-plugin",
        200,
        {},
        'echo "  eve connect"\n',
    )

    assert not result.ok
    assert "missing INSTALL_SOURCE=\"claude-code-plugin\"" in result.errors
    assert "missing config set-install-source" in result.errors
    assert "missing source-tagged connect command" in result.errors


def test_remote_probe_accepts_query_preserving_auth_redirect() -> None:
    result = probe.validate_response(
        "claude-desktop",
        307,
        {
            "location": (
                "/auth/login?"
                "returnTo=%2Fapp%2Fconnect%3Ftool%3Dclaude-desktop%26install_source%3Dclaude-desktop"
                "&install_source=claude-desktop"
            )
        },
        "",
    )

    assert result.ok
    assert result.errors == []


def test_remote_probe_rejects_auth_redirect_that_drops_query_state() -> None:
    result = probe.validate_response(
        "chatgpt-app",
        307,
        {"location": "/auth/login?returnTo=%2Fapp%2Fconnect"},
        "",
    )

    assert not result.ok
    assert "missing top-level install_source=chatgpt-app" in result.errors
    assert "returnTo missing install_source=chatgpt-app" in result.errors


def test_report_requires_every_entrypoint_to_pass() -> None:
    report = probe.build_report(
        [
            probe.ProbeResult(
                channel="claude-code-plugin",
                url="https://evemem.com/install?install_source=claude-code-plugin",
                status_code=200,
                ok=True,
                errors=[],
            ),
            probe.ProbeResult(
                channel="chatgpt-app",
                url="https://evemem.com/app/connect?install_source=chatgpt-app",
                status_code=307,
                ok=False,
                errors=["returnTo missing install_source=chatgpt-app"],
            ),
        ]
    )

    assert report["ok"] is False
    assert report["passed"] == 1
    assert report["failed"] == 1


def test_artifact_report_includes_non_promotion_deployment_gate() -> None:
    report = probe.build_artifact_report(
        [
            probe.ProbeResult(
                channel="claude-code-plugin",
                url="https://evemem.com/install?install_source=claude-code-plugin",
                status_code=200,
                ok=False,
                errors=["missing INSTALL_SOURCE=\"claude-code-plugin\""],
            )
        ],
        base_url="https://evemem.com",
        command="python3 scripts/deployment/verify_pack12_entrypoints.py --base-url https://evemem.com",
        checked_at="2026-06-17T00:00:00Z",
    )

    assert report["pack"] == "PACK-12"
    assert report["artifact"] == "production-entrypoint-probe"
    assert report["checked_at"] == "2026-06-17T00:00:00Z"
    assert report["base_url"] == "https://evemem.com"
    assert report["command"] == (
        "python3 scripts/deployment/verify_pack12_entrypoints.py --base-url https://evemem.com"
    )
    assert report["ok"] is False
    assert report["promotion_ready"] is False
    assert "Do not promote" in report["decision"]
    assert report["deployment_gate"]["status"] == "blocked"
    assert report["deployment_gate"]["github_workflow"] == ".github/workflows/deploy-managed-mvp.yml"
    assert report["deployment_gate"]["output_artifact"] == (
        "docs/specs/artifacts/pack12-production-entrypoint-probe-2026-06-17.json"
    )
    assert report["deployment_gate"]["github_upload_artifact"] == "pack12-production-entrypoint-probe"


def test_artifact_report_marks_deployment_gate_validated_after_success() -> None:
    report = probe.build_artifact_report(
        [
            probe.ProbeResult(
                channel="claude-code-plugin",
                url="https://evemem.com/install?install_source=claude-code-plugin",
                status_code=200,
                ok=True,
                errors=[],
            )
        ],
        base_url="https://evemem.com",
        command="python3 scripts/deployment/verify_pack12_entrypoints.py --base-url https://evemem.com",
        checked_at="2026-06-17T00:00:00Z",
    )

    assert report["ok"] is True
    assert report["promotion_ready"] is False
    assert report["deployment_gate"]["status"] == "validated"
    assert "clears entry URL routing only" in report["decision"]


def test_write_report_persists_json_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / "probe.json"
    report = probe.build_artifact_report(
        [
            probe.ProbeResult(
                channel="claude-code-plugin",
                url="https://evemem.com/install?install_source=claude-code-plugin",
                status_code=200,
                ok=True,
                errors=[],
            )
        ],
        base_url="http://localhost:3000",
        command="probe command",
        checked_at="2026-06-17T00:00:00Z",
    )

    probe.write_report(output_path, report)

    assert json.loads(output_path.read_text(encoding="utf-8")) == report


def test_local_http_entrypoint_probe_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-local-http-entrypoint-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "local-http-entrypoint-probe"
    assert artifact["target_base_url"] == "http://localhost:3107"
    assert artifact["ok"] is True
    assert artifact["passed"] == 4
    assert artifact["failed"] == 0
    assert artifact["promotion_ready"] is False
    assert artifact["production_status"] == "blocked"
    assert "not clean-machine" in artifact["scope"]


def test_production_entrypoint_probe_artifact_is_command_generated_entrypoint_pass() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-production-entrypoint-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "production-entrypoint-probe"
    assert artifact["base_url"] == "https://evemem.com"
    assert "--output docs/specs/artifacts/pack12-production-entrypoint-probe-2026-06-17.json" in artifact["command"]
    assert artifact["promotion_ready"] is False
    assert artifact["ok"] is True
    assert artifact["passed"] == 4
    assert artifact["failed"] == 0
    assert artifact["deployment_gate"]["status"] == "validated"
    assert "do not promote channels without actual host smoke evidence" in artifact["decision"]
