from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_pack12_smoke_matrix import (
    REMAINING_REQUIRED_CHANNELS,
    REQUIRED_CHANNELS,
    REQUIRED_SMOKE_CHECKS,
    validate_remaining_smoke_matrix,
    validate_smoke_matrix,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = REPO_ROOT.parents[1]
MONOREPO_ARTIFACTS_ROOT = MONOREPO_ROOT / "docs" / "specs" / "artifacts"

if not MONOREPO_ARTIFACTS_ROOT.exists():
    pytest.skip(
        "monorepo Pack 12 evidence artifacts are not available",
        allow_module_level=True,
    )


def test_active_pack12_smoke_matrix_tracks_first_wave_and_openai_channels() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-first-wave-smoke-matrix-2026-06-17.json"
    )

    result = validate_smoke_matrix(artifact_path)

    assert result.ok
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "first-wave-channel-smoke-matrix"
    assert artifact["promotion_ready"] is False

    channels = {channel["id"]: channel for channel in artifact["channels"]}
    assert list(channels) == list(REQUIRED_CHANNELS)
    for channel_id, expected_source in REQUIRED_CHANNELS.items():
        channel = channels[channel_id]
        assert channel["install_source"] == expected_source
        assert channel["promotion_ready"] is False
        assert set(channel["checks"]) == set(REQUIRED_SMOKE_CHECKS)
        if channel_id == "claude-code-plugin":
            assert all(
                status in {"pass", "blocked"} for status in channel["checks"].values()
            )
            assert channel["checks"]["clean_environment"] == "pass"
            assert channel["checks"]["entry_url"] == "pass"
            assert channel["checks"]["install_or_import"] == "pass"
            assert channel["checks"]["install_source_flow"] == "pass"
            assert channel["checks"]["rollback_or_uninstall"] == "blocked"
        elif channel_id == "claude-desktop":
            assert all(
                status in {"pass", "blocked"} for status in channel["checks"].values()
            )
            assert channel["checks"]["clean_environment"] == "pass"
            assert channel["checks"]["entry_url"] == "pass"
            assert channel["checks"]["install_or_import"] == "blocked"
            assert channel["checks"]["install_source_flow"] == "blocked"
            assert channel["checks"]["rollback_or_uninstall"] == "blocked"
        else:
            assert all(status == "not_run" for status in channel["checks"].values())

    production_probe = json.loads(
        (
            MONOREPO_ROOT
            / "docs"
            / "specs"
            / "artifacts"
            / "pack12-production-entrypoint-probe-2026-06-17.json"
        ).read_text(encoding="utf-8")
    )
    assert production_probe["ok"] is True
    assert production_probe["passed"] == 4
    assert production_probe["deployment_gate"]["status"] == "validated"

    for channel_id, channel in channels.items():
        assert channel["production_entrypoint_probe_artifact"] == (
            "docs/specs/artifacts/pack12-production-entrypoint-probe-2026-06-17.json"
        )
        if channel_id not in {"claude-code-plugin", "claude-desktop"}:
            assert channel["checks"]["entry_url"] == "not_run"
            assert not channel.get("blocked_by")

    claude_code = channels["claude-code-plugin"]
    assert claude_code["semantic_mcp_smoke_artifact"] == (
        "docs/specs/artifacts/pack12-claude-code-plugin-semantic-mcp-smoke-2026-06-17.json"
    )
    assert claude_code["partial_host_smoke_artifact"] == (
        "docs/specs/artifacts/pack12-claude-code-plugin-host-smoke-2026-06-17-public-client-0.3.3-v2.json"
    )
    assert claude_code["partial_host_smoke_gate_artifact"] == (
        "docs/specs/artifacts/pack12-claude-code-plugin-host-smoke-gate-2026-06-17-public-client-0.3.3-v2.json"
    )
    assert claude_code["host_capability_probe_artifact"] == (
        "docs/specs/artifacts/pack12-claude-code-plugin-host-capability-probe-2026-06-17.json"
    )
    assert claude_code["client_release_boundary_artifact"] == (
        "docs/specs/artifacts/pack12-client-release-boundary-2026-06-17.json"
    )
    assert "semantic MCP store/search/forget is proven" in claude_code["probe"]["observed"]
    assert "public-client host smoke now passes" in claude_code["probe"]["observed"]
    assert "naive Claude run would be contaminated" in claude_code["probe"]["observed"]
    assert "still not promoted" in claude_code["probe"]["observed"]
    assert claude_code["checks"]["install_or_import"] == "pass"
    assert claude_code["checks"]["store"] == "blocked"
    assert claude_code["checks"]["read"] == "blocked"
    assert claude_code["checks"]["forget"] == "blocked"
    assert claude_code["checks"]["connector_install_completed"] == "blocked"
    assert "0.3.3 clears" in claude_code["blocked_by"][0]
    assert "existing user-level Eve MCP server" in claude_code["blocked_by"][1]
    assert "authenticated Claude Code host session" in claude_code["blocked_by"][2]

    claude_desktop = channels["claude-desktop"]
    assert claude_desktop["remote_mcp_auth_probe_artifact"] == (
        "docs/specs/artifacts/pack12-claude-desktop-remote-mcp-auth-probe-2026-06-17.json"
    )
    assert claude_desktop["host_capability_probe_artifact"] == (
        "docs/specs/artifacts/pack12-claude-desktop-host-capability-probe-2026-06-17.json"
    )
    assert "Claude Desktop app is installed" in claude_desktop["probe"]["observed"]
    assert "no existing Eve MCP server" in claude_desktop["blocked_by"][0]
    assert "hosted MCP/auth boundary" in claude_desktop["blocked_by"][1]
    assert "connector import" in claude_desktop["blocked_by"][2]


def test_pack12_smoke_matrix_rejects_promoted_channel_without_full_smoke(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "smoke.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pack": "PACK-12",
                "artifact": "first-wave-channel-smoke-matrix",
                "promotion_ready": False,
                "channels": [
                    {
                        "id": "claude-code-plugin",
                        "install_source": "claude-code-plugin",
                        "promotion_ready": True,
                        "checks": {
                            check: "pass" for check in REQUIRED_SMOKE_CHECKS
                        }
                        | {"store": "not_run"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_smoke_matrix(artifact_path)

    assert not result.ok
    assert "claude-code-plugin is promotion_ready but store is not pass" in result.errors


def test_pack12_smoke_matrix_rejects_matrix_promotion_before_all_channels_pass(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "smoke.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pack": "PACK-12",
                "artifact": "first-wave-channel-smoke-matrix",
                "promotion_ready": True,
                "channels": [
                    {
                        "id": "claude-code-plugin",
                        "install_source": "claude-code-plugin",
                        "promotion_ready": False,
                        "checks": {check: "not_run" for check in REQUIRED_SMOKE_CHECKS},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_smoke_matrix(artifact_path)

    assert not result.ok
    assert "matrix is promotion_ready but claude-code-plugin is not" in result.errors


def test_pack12_smoke_matrix_rejects_promoted_channel_without_actual_evidence(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "smoke.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pack": "PACK-12",
                "artifact": "first-wave-channel-smoke-matrix",
                "promotion_ready": False,
                "channels": [
                    {
                        "id": "claude-code-plugin",
                        "install_source": "claude-code-plugin",
                        "promotion_ready": True,
                        "checks": {check: "pass" for check in REQUIRED_SMOKE_CHECKS},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_smoke_matrix(artifact_path)

    assert not result.ok
    assert (
        "claude-code-plugin is promotion_ready but proof_scope is not actual_host_smoke"
        in result.errors
    )
    assert (
        "claude-code-plugin is promotion_ready but smoke_evidence_artifact is missing"
        in result.errors
    )


def test_active_pack12_remaining_smoke_matrix_tracks_all_remaining_channels() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-remaining-channel-smoke-matrix-2026-06-17.json"
    )

    result = validate_remaining_smoke_matrix(artifact_path)

    assert result.ok
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "remaining-channel-smoke-matrix"
    assert artifact["promotion_ready"] is False

    channels = {channel["id"]: channel for channel in artifact["channels"]}
    assert list(channels) == list(REMAINING_REQUIRED_CHANNELS)
    for channel_id, expected_source in REMAINING_REQUIRED_CHANNELS.items():
        channel = channels[channel_id]
        assert channel["install_source"] == expected_source
        assert channel["promotion_ready"] is False
        assert set(channel["checks"]) == set(REQUIRED_SMOKE_CHECKS)
        assert all(
            status in {"not_run", "blocked"} for status in channel["checks"].values()
        )
        assert "pass" not in set(channel["checks"].values())

    assert channels["install-button-cursor"]["checks"]["entry_url"] == "blocked"
    assert channels["install-button-vscode"]["checks"]["entry_url"] == "blocked"


def test_pack12_remaining_smoke_matrix_rejects_unknown_or_missing_remaining_channel(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "remaining-smoke.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pack": "PACK-12",
                "artifact": "remaining-channel-smoke-matrix",
                "promotion_ready": False,
                "channels": [
                    {
                        "id": "install-button-cursor",
                        "install_source": "install-button-cursor",
                        "promotion_ready": False,
                        "checks": {check: "not_run" for check in REQUIRED_SMOKE_CHECKS},
                    },
                    {
                        "id": "unplanned-channel",
                        "install_source": "cursor",
                        "promotion_ready": False,
                        "checks": {check: "not_run" for check in REQUIRED_SMOKE_CHECKS},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_remaining_smoke_matrix(artifact_path)

    assert not result.ok
    assert "unexpected channel id: unplanned-channel" in result.errors
    assert "missing required channel: gemini-cli-extension" in result.errors
