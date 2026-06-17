from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_pack12_remote_entrypoint_smoke import (
    REQUIRED_REMOTE_CHANNELS,
    REQUIRED_REMOTE_LOCAL_CHECKS,
    validate_remote_entrypoint_smoke,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = REPO_ROOT.parents[1]
MONOREPO_ARTIFACTS_ROOT = MONOREPO_ROOT / "docs" / "specs" / "artifacts"

if not MONOREPO_ARTIFACTS_ROOT.exists():
    pytest.skip(
        "monorepo Pack 12 evidence artifacts are not available",
        allow_module_level=True,
    )


def test_pack12_remote_entrypoint_local_smoke_artifact_is_valid() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-remote-entrypoint-local-smoke-2026-06-17.json"
    )

    result = validate_remote_entrypoint_smoke(artifact_path)

    assert result.ok
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "remote-entrypoint-local-smoke"
    assert artifact["promotion_ready"] is False
    assert artifact["production_status"] == "blocked"

    channels = {channel["id"]: channel for channel in artifact["channels"]}
    assert list(channels) == list(REQUIRED_REMOTE_CHANNELS)
    for channel_id, install_source in REQUIRED_REMOTE_CHANNELS.items():
        channel = channels[channel_id]
        assert channel["install_source"] == install_source
        assert channel["promotion_ready"] is False
        assert set(channel["local_checks"]) == set(REQUIRED_REMOTE_LOCAL_CHECKS)
        assert all(status == "pass" for status in channel["local_checks"].values())


def test_pack12_remote_entrypoint_smoke_rejects_promotion_from_local_only_evidence(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "remote-entrypoint-smoke.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pack": "PACK-12",
                "artifact": "remote-entrypoint-local-smoke",
                "promotion_ready": True,
                "production_status": "blocked",
                "channels": [
                    {
                        "id": "claude-desktop",
                        "install_source": "claude-desktop",
                        "promotion_ready": False,
                        "local_checks": {
                            check: "pass" for check in REQUIRED_REMOTE_LOCAL_CHECKS
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_remote_entrypoint_smoke(artifact_path)

    assert not result.ok
    assert "local-only remote entrypoint smoke cannot set promotion_ready=true" in result.errors
