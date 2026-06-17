from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_pack12_smoke_plan_templates import (
    FIRST_WAVE_TEMPLATE_CHANNELS,
    REMAINING_TEMPLATE_CHANNELS,
    SECOND_WAVE_TEMPLATE_CHANNELS,
    validate_first_wave_smoke_plan_templates,
    validate_remaining_smoke_plan_templates,
    validate_second_wave_smoke_plan_templates,
    validate_smoke_plan_template_payload,
)
from scripts.validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_first_wave_smoke_plan_templates_are_fail_closed_and_complete() -> None:
    templates_dir = REPO_ROOT / "smoke-plans" / "pack12"

    result = validate_first_wave_smoke_plan_templates(templates_dir)

    assert result.ok, result.errors
    assert result.template_paths == {
        channel: templates_dir / f"{channel}.actual-host-template.json"
        for channel in FIRST_WAVE_TEMPLATE_CHANNELS
    }

    for channel, path in result.template_paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pack"] == "PACK-12"
        assert payload["artifact"] == "channel-smoke-plan-template"
        assert payload["channel"] == channel
        assert payload["install_source"] == FIRST_WAVE_TEMPLATE_CHANNELS[channel]
        assert payload["proof_scope"] == "actual_host_smoke"
        assert payload["promotion_ready"] is False
        assert payload["operator_required"] is True
        assert payload["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
        assert set(payload["steps"]) == set(REQUIRED_SMOKE_CHECKS)
        assert all("command" not in step for step in payload["steps"].values())


def test_claude_code_template_uses_plugin_supported_search_for_read_gate() -> None:
    template_path = (
        REPO_ROOT
        / "smoke-plans"
        / "pack12"
        / "claude-code-plugin.actual-host-template.json"
    )
    payload = json.loads(template_path.read_text(encoding="utf-8"))

    read_step = payload["steps"]["read"]

    assert "memory_search" in read_step["must_contain"]
    assert "memory_read" not in read_step["must_contain"]
    assert "store=semantic" in " ".join(read_step["command_template"])


def test_second_wave_smoke_plan_templates_are_fail_closed_and_complete() -> None:
    templates_dir = REPO_ROOT / "smoke-plans" / "pack12"

    result = validate_second_wave_smoke_plan_templates(templates_dir)

    assert result.ok, result.errors
    assert result.template_paths == {
        channel: templates_dir / f"{channel}.actual-host-template.json"
        for channel in SECOND_WAVE_TEMPLATE_CHANNELS
    }

    for channel, path in result.template_paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pack"] == "PACK-12"
        assert payload["artifact"] == "channel-smoke-plan-template"
        assert payload["channel"] == channel
        assert payload["install_source"] == SECOND_WAVE_TEMPLATE_CHANNELS[channel]
        assert payload["proof_scope"] == "actual_host_smoke"
        assert payload["promotion_ready"] is False
        assert payload["operator_required"] is True
        assert payload["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
        assert set(payload["steps"]) == set(REQUIRED_SMOKE_CHECKS)
        assert all("command" not in step for step in payload["steps"].values())


def test_remaining_channel_smoke_plan_templates_are_fail_closed_and_complete() -> None:
    templates_dir = REPO_ROOT / "smoke-plans" / "pack12"

    result = validate_remaining_smoke_plan_templates(templates_dir)

    assert result.ok, result.errors
    assert result.template_paths == {
        channel: templates_dir / f"{channel}.actual-host-template.json"
        for channel in REMAINING_TEMPLATE_CHANNELS
    }

    for channel, path in result.template_paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pack"] == "PACK-12"
        assert payload["artifact"] == "channel-smoke-plan-template"
        assert payload["channel"] == channel
        assert payload["install_source"] == REMAINING_TEMPLATE_CHANNELS[channel]
        assert payload["proof_scope"] == "actual_host_smoke"
        assert payload["promotion_ready"] is False
        assert payload["operator_required"] is True
        assert payload["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
        assert set(payload["steps"]) == set(REQUIRED_SMOKE_CHECKS)
        assert all("command" not in step for step in payload["steps"].values())


def test_smoke_plan_template_rejects_promotion_ready_payload() -> None:
    payload = _template_payload()
    payload["promotion_ready"] = True

    result = validate_smoke_plan_template_payload(payload, expected_channel="claude-code-plugin")

    assert not result.ok
    assert "claude-code-plugin template must not be promotion_ready" in result.errors


def test_smoke_plan_template_rejects_runnable_commands() -> None:
    payload = _template_payload()
    payload["steps"]["store"]["command"] = ["python3", "-c", "print('fake pass')"]

    result = validate_smoke_plan_template_payload(payload, expected_channel="claude-code-plugin")

    assert not result.ok
    assert "claude-code-plugin store must use command_template, not command" in result.errors


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
        "matrix_artifact": "docs/specs/artifacts/pack12-first-wave-smoke-matrix-2026-06-17.json",
        "evidence_artifact_template": "docs/specs/artifacts/pack12-claude-code-plugin-host-smoke-{timestamp}.json",
        "not_promoted": [
            "Template only; actual host smoke evidence has not been produced."
        ],
        "steps": {
            check: {
                "purpose": f"Prove {check}.",
                "command_template": ["operator-run", check],
                "required_env": ["EVE_PACK12_TARGET"],
                "must_contain": [check],
                "timeout_seconds": 120,
            }
            for check in REQUIRED_SMOKE_CHECKS
        },
    }
