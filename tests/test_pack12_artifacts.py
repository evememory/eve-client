from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_pack12_artifacts import validate_artifact_tree


REPO_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = REPO_ROOT.parents[1]
MONOREPO_ARTIFACTS_ROOT = MONOREPO_ROOT / "docs" / "specs" / "artifacts"

if not MONOREPO_ARTIFACTS_ROOT.exists():
    pytest.skip(
        "monorepo Pack 12 evidence artifacts are not available",
        allow_module_level=True,
    )


def test_missing_pack12_artifact_tree_fails(tmp_path: Path) -> None:
    result = validate_artifact_tree(tmp_path)

    assert not result.ok
    assert "plugins/claude-code/.claude-plugin/plugin.json" in result.errors


def test_minimal_pack12_artifact_tree_passes(tmp_path: Path) -> None:
    (tmp_path / "plugins/claude-code/.claude-plugin").mkdir(parents=True)
    (tmp_path / "plugins/claude-code/.claude-plugin/plugin.json").write_text(
        json.dumps(
            {
                "name": "eve-memory",
                "version": "0.0.1",
                "description": "Eve Memory for Claude Code",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plugins/claude-code/.mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "eve-memory": {
                        "command": "eve-mcp-server",
                        "env": {"EVE_MCP_BASE_URL": "https://mcp.evemem.com/mcp"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plugins/claude-code/skills/eve-memory").mkdir(parents=True)
    (tmp_path / "plugins/claude-code/skills/eve-memory/SKILL.md").write_text(
        "---\n"
        "name: eve-memory\n"
        "description: Use Eve Memory from Claude Code.\n"
        "---\n"
        "# Eve Memory\n",
        encoding="utf-8",
    )
    (tmp_path / "plugins/claude-code/hooks").mkdir(parents=True)
    (tmp_path / "plugins/claude-code/hooks/hooks.json").write_text(
        json.dumps({"hooks": {}}),
        encoding="utf-8",
    )
    (tmp_path / "plugins/claude-code/README.md").write_text(
        "# Eve Memory for Claude Code\n",
        encoding="utf-8",
    )
    (tmp_path / "connectors/claude-desktop").mkdir(parents=True)
    (tmp_path / "connectors/claude-desktop/README.md").write_text(
        "# Claude Desktop Connector\n\n"
        "Remote MCP endpoint: https://mcp.evemem.com/mcp\n",
        encoding="utf-8",
    )
    (tmp_path / "plugins/codex/.codex-plugin").mkdir(parents=True)
    (tmp_path / "plugins/codex/.codex-plugin/plugin.json").write_text(
        json.dumps(
            {
                "name": "eve-memory",
                "version": "0.0.1",
                "description": "Eve Memory for Codex",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plugins/codex/.mcp.json").write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "eve-memory": {"url": "https://mcp.evemem.com/mcp"}
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plugins/codex/skills/eve-memory").mkdir(parents=True)
    (tmp_path / "plugins/codex/skills/eve-memory/SKILL.md").write_text(
        "---\n"
        "name: eve-memory\n"
        "description: Use Eve Memory from Codex.\n"
        "---\n"
        "# Eve Memory\n",
        encoding="utf-8",
    )
    (tmp_path / "plugins/codex/README.md").write_text(
        "# Eve Memory for Codex\n",
        encoding="utf-8",
    )
    (tmp_path / "extensions/eve-memory").mkdir(parents=True)
    (tmp_path / "extensions/eve-memory/gemini-extension.json").write_text(
        json.dumps(
            {
                "name": "eve-memory",
                "version": "0.0.1",
                "mcpServers": {
                    "eve-memory": {
                        "httpUrl": "https://mcp.evemem.com/mcp",
                    }
                },
                "contextFileName": "GEMINI.md",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "extensions/eve-memory/GEMINI.md").write_text(
        "# Eve Memory for Gemini CLI\n",
        encoding="utf-8",
    )
    (tmp_path / "extensions/eve-memory/README.md").write_text(
        "# Eve Memory Gemini CLI Extension\n",
        encoding="utf-8",
    )

    result = validate_artifact_tree(tmp_path)

    assert result.ok
    assert result.errors == []


def test_claude_code_plugin_artifacts_are_valid() -> None:
    plugin_root = REPO_ROOT / "plugins" / "claude-code"
    manifest = json.loads(
        (plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    mcp_config = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    skill = (plugin_root / "skills" / "eve-memory" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    readme = (plugin_root / "README.md").read_text(encoding="utf-8")

    assert manifest["name"] == "eve-memory"
    assert manifest["defaultEnabled"] is False
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "hooks" not in manifest

    server = mcp_config["mcpServers"]["eve-memory"]
    assert server == {
        "command": "eve-mcp-server",
        "env": {"EVE_MCP_BASE_URL": "https://mcp.evemem.com/mcp"},
    }
    assert "X-API-Key" not in json.dumps(mcp_config)
    assert "Authorization" not in json.dumps(mcp_config)

    assert hooks["hooks"]["SessionStart"][0]["matcher"] == "startup|resume"
    assert hooks["hooks"]["SessionStart"][0]["hooks"][0] == {
        "type": "command",
        "command": "eve-claude-hook session_start",
        "timeout": 5,
    }
    assert hooks["hooks"]["SessionEnd"][0]["hooks"][0]["async"] is True
    assert hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] == 5

    assert "Do not store API keys" in skill
    assert "No API key or token is embedded" in readme
    assert "https://evemem.com/install?install_source=claude-code-plugin" in readme


def test_claude_code_plugin_clean_profile_smoke_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-code-plugin-clean-profile-smoke-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "claude-code-plugin"
    assert artifact["artifact"] == "clean-profile-plugin-package-smoke"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["scope"] == "Local clean-profile package integrity only; not Claude Code marketplace install evidence and not store/read/forget smoke."
    assert artifact["checks"] == {
        "clean_environment": "pass",
        "plugin_manifest": "pass",
        "referenced_files_exist": "pass",
        "mcp_config": "pass",
        "hooks": "pass",
        "skill": "pass",
        "readme": "pass",
        "no_embedded_secrets": "pass",
    }
    assert set(artifact["remaining_before_promotion"]) == {
        "Claude Code plugin install through the actual Claude Code plugin mechanism",
        "eve connect --tool claude-code --install-source claude-code-plugin against production",
        "MCP store/read/forget smoke from the connected Claude Code environment",
        "connector.install.completed and signup_source attribution proof",
        "rollback/uninstall proof from a clean profile",
    }


def test_claude_code_plugin_semantic_mcp_smoke_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-code-plugin-semantic-mcp-smoke-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "claude-code-plugin"
    assert artifact["artifact"] == "claude-code-plugin-semantic-mcp-smoke"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["scope"] == (
        "Claude Code plugin-namespaced semantic MCP store/search/forget only; "
        "not clean-profile install/source/rollback evidence."
    )
    assert artifact["plugin_mcp_server"] == "plugin:eve-memory:eve-memory"
    assert artifact["tool_namespace"] == "mcp__plugin_eve-memory_eve-memory"
    assert artifact["checks"] == {
        "plugin_loaded": "pass",
        "store_semantic": "pass",
        "search_read_before_forget": "pass",
        "forget": "pass",
        "search_absent_after_forget": "pass",
    }
    assert artifact["smoke_result"]["stored"] is True
    assert artifact["smoke_result"]["found_before_forget"] is True
    assert artifact["smoke_result"]["forgotten"] is True
    assert artifact["smoke_result"]["found_after_forget"] is False
    assert artifact["auto_store_control"]["promotion_impact"] == "none"
    assert set(artifact["remaining_before_promotion"]) == {
        "clean Claude Code profile install/import evidence",
        "source-tagged connect/auth evidence",
        "install_source=claude-code-plugin attribution proof",
        "connector.install.completed audit/metric proof",
        "rollback/uninstall proof from the clean profile",
        "channel-smoke-evidence produced by the Pack 12 smoke runner",
    }


def test_claude_code_plugin_public_client_release_blocker_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-code-plugin-host-smoke-2026-06-17-public-client-release-blocker.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "channel-smoke-evidence"
    assert artifact["channel"] == "claude-code-plugin"
    assert artifact["proof_scope"] == "actual_host_smoke"
    assert artifact["promotion_ready"] is False
    assert artifact["checks"]["clean_environment"] == "pass"
    assert artifact["checks"]["entry_url"] == "pass"
    assert artifact["checks"]["install_or_import"] == "fail"
    failed_install = next(
        step for step in artifact["step_results"] if step["check"] == "install_or_import"
    )
    assert failed_install["return_code"] == 2
    assert "eve-memory-client==0.3.0" in failed_install["stderr_preview"]
    assert "No such command 'config'" in failed_install["stderr_preview"]


def test_claude_code_plugin_public_client_0_3_3_partial_smoke_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-code-plugin-host-smoke-2026-06-17-public-client-0.3.3-v2.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "channel-smoke-evidence"
    assert artifact["channel"] == "claude-code-plugin"
    assert artifact["proof_scope"] == "actual_host_smoke"
    assert artifact["promotion_ready"] is False
    assert artifact["checks"]["clean_environment"] == "pass"
    assert artifact["checks"]["entry_url"] == "pass"
    assert artifact["checks"]["install_or_import"] == "pass"
    assert artifact["checks"]["install_source_flow"] == "pass"
    assert artifact["checks"]["connect"] == "fail"
    assert artifact["checks"]["store"] == "fail"
    assert artifact["checks"]["read"] == "fail"
    assert artifact["checks"]["forget"] == "fail"
    assert artifact["checks"]["connector_install_completed"] == "fail"
    assert artifact["checks"]["rollback_or_uninstall"] == "pass"
    assert artifact["not_promoted"] == ["connect failed"]

    install = next(
        step for step in artifact["step_results"] if step["check"] == "install_or_import"
    )
    assert "public-client-version=0.3.3" in install["stdout_preview"]

    install_source = next(
        step for step in artifact["step_results"] if step["check"] == "install_source_flow"
    )
    assert install_source["stdout_preview"] == "install_source=claude-code-plugin\n"

    rollback = next(
        step for step in artifact["step_results"] if step["check"] == "rollback_or_uninstall"
    )
    assert "partial-cleanup success" in rollback["stdout_preview"]
    assert "full plugin uninstall blocked" in rollback["stdout_preview"]


def test_claude_code_host_capability_probe_blocks_contaminated_promotion() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-code-plugin-host-capability-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "claude-code-plugin-host-capability-probe"
    assert artifact["channel"] == "claude-code-plugin"
    assert artifact["promotion_ready"] is False
    assert artifact["checks"]["claude_cli_present"] == "pass"
    assert artifact["checks"]["claude_plugin_validate"] == "pass"
    assert artifact["checks"]["existing_user_eve_mcp_detected"] == "pass"
    assert artifact["checks"]["session_plugin_dir_import_isolated"] == "fail"
    assert artifact["checks"]["functional_model_smoke"] == "fail"
    assert artifact["checks"]["synthetic_memory_cleanup"] == "pass"
    assert any(
        "existing user-level MCP config" in observation
        for observation in artifact["observations"]
    )
    assert any(
        "credential header value is intentionally omitted" in command["result"]
        for command in artifact["commands"]
    )
    assert any(
        "cannot prove Pack 12 plugin install/import" in reason
        for reason in artifact["not_promoted"]
    )


def test_pack12_client_release_boundary_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-client-release-boundary-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "client-release-boundary"
    assert artifact["distribution"] == "eve-memory-client"
    assert artifact["prepared_version"] == "0.3.3"
    assert artifact["published_version"] == "0.3.3"
    assert artifact["previous_published_version_blocking_smoke"] == "0.3.0"
    assert artifact["status"] == "published_verified_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["local_preparation"]["release_tag"] == "eve-memory-client@0.3.3"
    assert artifact["release_publication"]["status"] == "published"
    assert any(
        "does not promote the Claude Code channel" in reason
        for reason in artifact["not_promoted"]
    )
    assert any(
        "isolated uv tool install" in validation["command"]
        and "0.3.3" in validation["result"]
        for validation in artifact["validations"]
    )


def test_channel_smoke_runner_readiness_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-channel-smoke-runner-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "channel-smoke-runner-readiness"
    assert artifact["promotion_ready"] is False
    assert artifact["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
    assert artifact["evidence_artifact"] == "channel-smoke-evidence"
    assert artifact["resume_supported"] is True
    assert artifact["redacts_command_and_output"] is True
    assert "actual_host_smoke proof_scope is required for promotion" in artifact["promotion_guards"]
    assert "clean-machine host smoke artifacts must still be produced per channel" in artifact["remaining_before_promotion"]


def test_channel_smoke_matrix_updater_readiness_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-smoke-matrix-updater-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "smoke-matrix-updater-readiness"
    assert artifact["promotion_ready"] is False
    assert artifact["updater"] == "packages/client/scripts/apply_pack12_channel_smoke_evidence.py"
    assert artifact["requires_proof_scope"] == "actual_host_smoke"
    assert "local_dry_run evidence is rejected" in artifact["promotion_guards"]
    assert "actual host smoke still has to be run per channel" in artifact["remaining_before_promotion"]


def test_channel_smoke_plan_materializer_readiness_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-smoke-plan-materializer-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "smoke-plan-materializer-readiness"
    assert artifact["status"] == "materializer_ready_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["materializer"] == "packages/client/scripts/materialize_pack12_channel_smoke_plan.py"
    assert artifact["input_artifact"] == "channel-smoke-plan-template"
    assert artifact["output_artifact"] == "channel-smoke-plan"
    assert "does not execute commands" in artifact["promotion_guards"]
    assert "channel-smoke-evidence still has to be produced by the runner" in artifact[
        "remaining_before_promotion"
    ]


def test_smoke_gate_orchestrator_readiness_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-smoke-gate-orchestrator-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "smoke-gate-orchestrator-readiness"
    assert artifact["status"] == "orchestrator_ready_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["orchestrator"] == "packages/client/scripts/run_pack12_channel_smoke_gate.py"
    assert "channel-smoke-evidence" in artifact["output_artifacts"]
    assert "failed smoke leaves the matrix unchanged" in artifact["promotion_guards"]
    assert "actual host smoke must pass per channel through this gate or the underlying runner/updater sequence" in artifact[
        "remaining_before_promotion"
    ]


def test_readiness_rollup_verifier_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-readiness-rollup-verifier-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "readiness-rollup-verifier"
    assert artifact["status"] == "verifier_ready_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["verifier"] == "packages/client/scripts/validate_pack12_readiness_rollup.py"
    assert "readiness artifacts must not be promotion_ready" in artifact[
        "promotion_guards"
    ]
    assert "actual host smoke still has to be run per channel" in artifact[
        "remaining_before_promotion"
    ]


def test_first_wave_smoke_plan_template_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-first-wave-smoke-plan-templates-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "first-wave-smoke-plan-templates"
    assert artifact["status"] == "templates_ready_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["validator"] == "packages/client/scripts/validate_pack12_smoke_plan_templates.py"
    assert artifact["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
    assert artifact["template_channels"] == [
        "claude-code-plugin",
        "claude-desktop",
    ]
    assert artifact["templates"] == {
        "claude-code-plugin": "packages/client/smoke-plans/pack12/claude-code-plugin.actual-host-template.json",
        "claude-desktop": "packages/client/smoke-plans/pack12/claude-desktop.actual-host-template.json",
    }
    assert "templates are not channel-smoke-evidence" in artifact["promotion_guards"]
    assert "convert template to a concrete channel-smoke-plan" in artifact[
        "remaining_before_promotion"
    ]


def test_second_wave_smoke_plan_template_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-second-wave-smoke-plan-templates-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "second-wave-smoke-plan-templates"
    assert artifact["status"] == "templates_ready_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["validator"] == "packages/client/scripts/validate_pack12_smoke_plan_templates.py"
    assert artifact["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
    assert artifact["template_channels"] == [
        "codex-plugin",
        "chatgpt-app",
    ]
    assert artifact["templates"] == {
        "codex-plugin": "packages/client/smoke-plans/pack12/codex-plugin.actual-host-template.json",
        "chatgpt-app": "packages/client/smoke-plans/pack12/chatgpt-app.actual-host-template.json",
    }
    assert "templates are not channel-smoke-evidence" in artifact["promotion_guards"]
    assert "convert template to a concrete channel-smoke-plan" in artifact[
        "remaining_before_promotion"
    ]


def test_remaining_channel_smoke_plan_template_artifact_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-remaining-channel-smoke-plan-templates-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "remaining-channel-smoke-plan-templates"
    assert artifact["status"] == "templates_ready_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["validator"] == "packages/client/scripts/validate_pack12_smoke_plan_templates.py"
    assert artifact["runner"] == "packages/client/scripts/run_pack12_channel_smoke.py"
    assert artifact["template_channels"] == [
        "install-button-cursor",
        "install-button-vscode",
        "gemini-cli-extension",
        "cursor",
        "vscode",
        "windsurf",
    ]
    assert artifact["templates"] == {
        "install-button-cursor": "packages/client/smoke-plans/pack12/install-button-cursor.actual-host-template.json",
        "install-button-vscode": "packages/client/smoke-plans/pack12/install-button-vscode.actual-host-template.json",
        "gemini-cli-extension": "packages/client/smoke-plans/pack12/gemini-cli-extension.actual-host-template.json",
        "cursor": "packages/client/smoke-plans/pack12/cursor.actual-host-template.json",
        "vscode": "packages/client/smoke-plans/pack12/vscode.actual-host-template.json",
        "windsurf": "packages/client/smoke-plans/pack12/windsurf.actual-host-template.json",
    }
    assert "templates are not channel-smoke-evidence" in artifact["promotion_guards"]
    assert "convert template to a concrete channel-smoke-plan" in artifact[
        "remaining_before_promotion"
    ]


def test_claude_desktop_connector_readiness_doc_is_remote_mcp_first() -> None:
    readme = (REPO_ROOT / "connectors" / "claude-desktop" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "https://mcp.evemem.com/mcp" in readme
    assert "https://evemem.com/app/connect?tool=claude-desktop&install_source=claude-desktop" in readme
    assert "Remote MCP is first" in readme
    assert "MCPB is a fallback" in readme
    assert "Do not submit to the Anthropic connector directory" in readme


def test_claude_desktop_readiness_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-desktop-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "claude-desktop-claude-ai"
    assert artifact["status"] == "planned_not_promoted"
    assert artifact["submission_ready"] is False
    assert artifact["mcpb_required"] is False
    assert artifact["remote_mcp_endpoint"] == "https://mcp.evemem.com/mcp"
    assert artifact["install_source"] == "claude-desktop"
    assert (
        artifact["managed_connect_url"]
        == "https://evemem.com/app/connect?tool=claude-desktop&install_source=claude-desktop"
    )
    assert set(artifact["required_before_submission"]) == {
        "OAuth account-selection smoke",
        "tool annotations audit",
        "privacy policy review",
        "clean store/read/forget smoke",
        "allowed links review if connector opens links",
    }


def test_claude_desktop_remote_mcp_auth_probe_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-desktop-remote-mcp-auth-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "claude-desktop"
    assert artifact["artifact"] == "remote-mcp-auth-boundary-probe"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["submission_ready"] is False
    assert artifact["checks"] == {
        "mcp_get_requires_auth": "pass",
        "mcp_initialize_requires_auth": "pass",
        "protected_resource_metadata": "pass",
        "auth0_openid_configuration": "pass",
        "no_tool_or_memory_leakage": "pass",
    }
    assert artifact["protected_resource_metadata"]["resource"] == "https://mcp.evemem.com/mcp"
    assert artifact["protected_resource_metadata"]["authorization_servers"] == [
        "https://evemem.us.auth0.com/"
    ]
    assert artifact["auth0_openid_configuration"]["issuer"] == "https://evemem.us.auth0.com/"
    assert artifact["remaining_before_promotion"] == [
        "production source-tagged /app/connect redirect must pass after UI deploy",
        "Claude Desktop or claude.ai connector import must complete against the hosted MCP endpoint",
        "OAuth/account-selection flow must produce a valid bearer token with the expected audience",
        "store/read/forget smoke must pass from the connected Claude environment",
        "connector.install.completed and signup_source attribution must be observed",
        "disconnect/rollback proof must exist",
    ]


def test_claude_desktop_host_capability_probe_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-claude-desktop-host-capability-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "claude-desktop"
    assert artifact["artifact"] == "claude-desktop-host-capability-probe"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["submission_ready"] is False
    assert artifact["checks"] == {
        "claude_desktop_app_present": "pass",
        "config_parseable": "pass",
        "no_existing_eve_mcp_server": "pass",
        "no_existing_eve_extension": "pass",
        "production_entrypoint": "pass",
        "remote_mcp_auth_boundary": "pass",
        "connector_import": "blocked",
        "oauth_account_selection": "blocked",
        "store_read_forget": "blocked",
        "connector_install_completed": "blocked",
        "rollback_or_uninstall": "blocked",
    }
    assert any(
        "no existing Eve MCP server" in observation
        for observation in artifact["observations"]
    )
    assert any(
        "connector import" in reason.lower()
        for reason in artifact["not_promoted"]
    )
    assert artifact["remaining_before_promotion"] == [
        "Claude Desktop or claude.ai connector import must complete against the hosted MCP endpoint.",
        "OAuth/account-selection flow must produce a valid bearer token with the expected audience.",
        "store/read/forget smoke must pass from the connected Claude environment.",
        "install_source=claude-desktop attribution must be observed.",
        "connector.install.completed telemetry must be observed.",
        "disconnect/rollback proof must exist.",
    ]


def test_codex_plugin_artifacts_are_valid() -> None:
    plugin_root = REPO_ROOT / "plugins" / "codex"
    manifest = json.loads(
        (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    mcp_config = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    skill = (plugin_root / "skills" / "eve-memory" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    readme = (plugin_root / "README.md").read_text(encoding="utf-8")

    assert manifest["name"] == "eve-memory"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["interface"]["displayName"] == "Eve Memory"
    assert "defaultPrompt" in manifest["interface"]

    server = mcp_config["mcp_servers"]["eve-memory"]
    assert server == {"url": "https://mcp.evemem.com/mcp"}
    assert "X-API-Key" not in json.dumps(mcp_config)
    assert "Authorization" not in json.dumps(mcp_config)

    assert "Do not store secrets" in skill
    assert "No API key or token is embedded" in readme
    assert "Codex hooks are not part of this v1 package" in readme
    assert "https://evemem.com/install?install_source=codex-plugin" in readme


def test_codex_plugin_clean_profile_smoke_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-codex-plugin-clean-profile-smoke-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "codex-plugin"
    assert artifact["artifact"] == "clean-profile-plugin-package-smoke"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["scope"] == "Local clean-profile package integrity only; not Codex plugin marketplace/install evidence and not store/read/forget smoke."
    assert artifact["checks"] == {
        "clean_environment": "pass",
        "plugin_manifest": "pass",
        "referenced_files_exist": "pass",
        "mcp_config": "pass",
        "skill": "pass",
        "readme": "pass",
        "hooks_excluded_v1": "pass",
        "no_embedded_secrets": "pass",
    }
    assert set(artifact["remaining_before_promotion"]) == {
        "Codex plugin install through the actual Codex plugin mechanism or approved repo-distributed plugin path",
        "eve connect --tool codex-cli --auth-mode oauth --install-source codex-plugin against production",
        "MCP store/read/forget smoke from the connected Codex environment",
        "connector.install.completed and signup_source attribution proof",
        "rollback/uninstall proof from a clean profile",
    }


def test_codex_plugin_host_capability_probe_blocks_direct_mcp_contamination() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-codex-plugin-host-capability-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "codex-plugin"
    assert artifact["artifact"] == "codex-plugin-host-capability-probe"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["checks"] == {
        "codex_cli_present": "pass",
        "pack12_plugin_source_present": "pass",
        "clean_profile_package_integrity": "pass",
        "codex_plugin_installed": "blocked",
        "existing_direct_eve_mcp_detected": "pass",
        "current_host_uncontaminated": "blocked",
        "oauth_connect": "blocked",
        "store_read_forget": "blocked",
        "connector_install_completed": "blocked",
        "rollback_or_uninstall": "blocked",
    }
    assert any(
        "direct eve-memory MCP server configured" in observation
        for observation in artifact["observations"]
    )
    assert any(
        "contaminated by a direct host MCP config" in reason
        for reason in artifact["not_promoted"]
    )
    assert artifact["remaining_before_promotion"] == [
        "Create a clean Codex profile without direct eve-memory MCP config.",
        "Install or load the Pack 12 Codex plugin through the actual Codex plugin mechanism or approved repo-distributed plugin path.",
        "Run eve connect --tool codex-cli --auth-mode oauth --install-source codex-plugin against production.",
        "Run store/read/forget smoke from the connected Codex plugin environment.",
        "Verify install_source=codex-plugin attribution and connector.install.completed telemetry.",
        "Run rollback/uninstall proof from the clean profile.",
    ]


def test_chatgpt_readiness_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-chatgpt-app-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "chatgpt-custom-mcp-app"
    assert artifact["status"] == "planned_not_promoted"
    assert artifact["developer_mode_validation_ready"] is False
    assert artifact["public_submission_ready"] is False
    assert artifact["remote_mcp_endpoint"] == "https://mcp.evemem.com/mcp"
    assert artifact["install_source"] == "chatgpt-app"
    assert (
        artifact["managed_connect_url"]
        == "https://evemem.com/app/connect?install_source=chatgpt-app"
    )
    assert artifact["host_capability_probe_artifact"] == (
        "docs/specs/artifacts/pack12-chatgpt-app-host-capability-probe-2026-06-17.json"
    )
    assert set(artifact["required_before_submission"]) == {
        "developer-mode import smoke",
        "OAuth or supported auth-mode confirmation",
        "tool annotation audit",
        "privacy and terms URL confirmation",
        "safe tool descriptions for read/write actions",
        "clean store/read/forget smoke",
    }
    assert artifact["tool_annotation_audit"]["read_tools"] == [
        "memory_search",
        "memory_read",
    ]
    assert artifact["tool_annotation_audit"]["write_tools"] == ["memory_store"]
    assert artifact["tool_annotation_audit"]["destructive_tools"] == ["memory_forget"]
    assert "not ChatGPT developer-mode validation" in artifact["tool_annotation_audit"][
        "observed"
    ]


def test_chatgpt_host_capability_probe_is_not_promotion_evidence() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-chatgpt-app-host-capability-probe-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "chatgpt-app"
    assert artifact["artifact"] == "chatgpt-app-host-capability-probe"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["checks"] == {
        "official_developer_mode_path_verified": "pass",
        "hosted_https_mcp_endpoint_documented": "pass",
        "tool_annotation_readiness": "pass",
        "production_entrypoint": "pass",
        "chatgpt_developer_mode_access": "blocked",
        "developer_mode_import": "blocked",
        "oauth_or_supported_auth_confirmation": "blocked",
        "tool_visibility": "blocked",
        "store_read_forget": "blocked",
        "connector_install_completed": "blocked",
        "rollback_or_disconnect": "blocked",
        "submission_policy_audit": "blocked",
    }
    source_urls = {source["url"] for source in artifact["official_sources"]}
    assert "https://developers.openai.com/apps-sdk/deploy/connect-chatgpt" in source_urls
    assert "https://developers.openai.com/api/docs/guides/developer-mode" in source_urls
    assert "https://developers.openai.com/apps-sdk/deploy/testing" in source_urls
    assert "https://developers.openai.com/apps-sdk/deploy/submission" in source_urls
    assert any(
        "repo shell cannot prove ChatGPT developer-mode access" in observation
        for observation in artifact["observations"]
    )
    assert any(
        "actual ChatGPT developer-mode import" in reason
        for reason in artifact["not_promoted"]
    )
    assert artifact["remaining_before_promotion"] == [
        "Enable or access ChatGPT developer mode in an eligible account or workspace.",
        "Create the Eve app/connector in ChatGPT using https://mcp.evemem.com/mcp.",
        "Confirm OAuth or supported auth mode works for Eve.",
        "Confirm expected Eve tools are visible with safe descriptions and annotations.",
        "Run store/read/forget smoke from the connected ChatGPT environment.",
        "Verify install_source=chatgpt-app attribution and connector.install.completed telemetry.",
        "Run disconnect/rollback proof.",
        "Complete submission/privacy/PII/tool-behavior audit before public publication.",
    ]


def test_remaining_channels_readiness_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-remaining-channels-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "remaining-channels-readiness"
    assert artifact["status"] == "planned_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["channel_order"] == [
        "install-buttons",
        "gemini-cli-extension",
        "cursor",
        "vscode",
        "windsurf",
    ]
    assert artifact["deferred_channels"] == ["jetbrains", "browser-extension"]
    assert "install_source propagated end to end" in artifact["shared_promotion_gates"]
    assert "clean-machine connect/store/read/forget smoke" in artifact[
        "shared_promotion_gates"
    ]

    channels = {channel["id"]: channel for channel in artifact["channels"]}
    assert channels["gemini-cli-extension"]["current_support"][
        "client_registry_provider"
    ] is True
    assert channels["gemini-cli-extension"]["current_support"][
        "extension_artifact"
    ] is True
    assert (
        channels["gemini-cli-extension"]["package_evidence_artifact"]
        == "docs/specs/artifacts/pack12-gemini-cli-extension-package-smoke-2026-06-17.json"
    )
    assert channels["cursor"]["current_support"]["client_registry_provider"] is True
    assert channels["cursor"]["current_support"]["config_writer"] is True
    assert channels["vscode"]["current_support"]["client_registry_provider"] is True
    assert channels["vscode"]["current_support"]["mcp_json_writer"] is True
    assert channels["windsurf"]["current_support"]["client_registry_provider"] is True
    assert channels["windsurf"]["current_support"]["mcp_config_writer"] is True
    assert all(channel["promotion_ready"] is False for channel in channels.values())
    assert all(
        channels[channel_id]["provider_evidence_artifact"]
        == "docs/specs/artifacts/pack12-third-wave-mcp-ide-providers-2026-06-17.json"
        for channel_id in ["cursor", "vscode", "windsurf"]
    )


def test_gemini_cli_extension_artifacts_are_valid() -> None:
    extension_root = REPO_ROOT / "extensions" / "eve-memory"
    manifest = json.loads(
        (extension_root / "gemini-extension.json").read_text(encoding="utf-8")
    )
    context = (extension_root / "GEMINI.md").read_text(encoding="utf-8")
    readme = (extension_root / "README.md").read_text(encoding="utf-8")
    manifest_json = json.dumps(manifest)

    assert manifest["name"] == "eve-memory"
    assert manifest["version"] == "0.1.0"
    assert manifest["contextFileName"] == "GEMINI.md"
    assert "trust" not in manifest_json

    server = manifest["mcpServers"]["eve-memory"]
    assert server["httpUrl"] == "https://mcp.evemem.com/mcp"
    assert server["headers"] == {"X-Source-Agent": "gemini_cli"}
    assert "X-API-Key" not in manifest_json
    assert "Authorization" not in manifest_json

    assert "Do not store secrets" in context
    assert "gemini extensions install" in readme
    assert "No API key or token is embedded" in readme


def test_gemini_cli_extension_package_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-gemini-cli-extension-package-smoke-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["channel"] == "gemini-cli-extension"
    assert artifact["artifact"] == "extension-package-smoke"
    assert artifact["ok"] is True
    assert artifact["promotion_ready"] is False
    assert artifact["scope"] == (
        "Local Gemini CLI extension package integrity only; not gemini extensions "
        "install evidence and not store/read/forget smoke."
    )
    assert artifact["checks"] == {
        "extension_manifest": "pass",
        "referenced_files_exist": "pass",
        "mcp_config": "pass",
        "context_file": "pass",
        "readme": "pass",
        "no_embedded_secrets": "pass",
    }
    assert set(artifact["remaining_before_promotion"]) == {
        "gemini extensions install from release source or clean local package path",
        "MCP connection/auth smoke from Gemini CLI using the extension",
        "MCP store/read/forget smoke from the connected Gemini CLI environment",
        "connector.install.completed and signup_source attribution proof",
        "rollback/uninstall proof with gemini extensions uninstall",
    }


def test_third_wave_mcp_ide_provider_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-third-wave-mcp-ide-providers-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "third-wave-mcp-ide-provider-implementation"
    assert artifact["status"] == "provider_planning_implemented_not_promoted"
    assert artifact["promotion_ready"] is False
    assert artifact["scope"] == (
        "Client-submodule install planning and config rendering for Cursor, VS Code, "
        "and Windsurf only; not clean-machine install/connect/store/read/forget smoke "
        "and not marketplace/listing evidence."
    )
    channels = {channel["id"]: channel for channel in artifact["implemented_channels"]}
    assert channels["cursor"]["config_root_key"] == "mcpServers"
    assert channels["vscode"]["config_root_key"] == "servers"
    assert channels["windsurf"]["config_root_key"] == "mcpServers"
    assert artifact["checks"] == {
        "detect_tools": "pass",
        "registry_provider_lookup": "pass",
        "install_plan_generation": "pass",
        "json_config_rendering": "pass",
        "installer_apply_path": "pass",
        "path_policy": "pass",
        "no_hooks_or_prompt_mutation": "pass",
        "no_embedded_secret_in_static_artifact": "pass",
    }
    assert "MCP store/read/forget smoke from each connected host" in artifact[
        "remaining_before_promotion"
    ]


def test_channel_analytics_readiness_artifact_is_not_promoted() -> None:
    artifact_path = (
        MONOREPO_ROOT
        / "docs"
        / "specs"
        / "artifacts"
        / "pack12-channel-analytics-readiness-2026-06-17.json"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["pack"] == "PACK-12"
    assert artifact["artifact"] == "channel-analytics-readiness"
    assert artifact["status"] == "partial_plumbing_not_promoted"
    assert artifact["dashboard_ready"] is False
    assert artifact["events"] == [
        "signup.install_source",
        "connector.install.completed",
    ]
    assert artifact["implemented"] == [
        "install_source accepted only from static channel allowlist",
        "install_source propagated from internal signup payload to managed tenant signup_source",
        "signup.provision success/duplicate metric uses normalized signup_source",
        "connector.install.completed authenticated event endpoint emits static install_source and connector labels",
        "memory.stored event includes tenant signup_source for first-memory funnel measurement",
        "generic entry-point propagation carries allowlisted install_source through /install, eve config set-install-source, hosted OAuth connect URL, protected-route login redirect, and Auth0 post-login provisioning payload",
        "Claude Code, Claude Desktop/claude.ai, Codex, and ChatGPT readiness docs or artifacts include source-tagged entry URLs",
        "Cursor install-button readiness uses data-install-source=install-button-cursor on the managed connect page",
    ]
    assert (
        "docs/specs/artifacts/pack12-remaining-channel-smoke-matrix-2026-06-17.json"
        in artifact["related_artifacts"]
    )
    assert artifact["required_before_promotion"] == [
        "each promoted channel button or listing must point to an allowlisted install_source URL and be exercised in clean install smoke",
        "per-channel dashboard or query saved against PACK-06 signup audit data",
        "connector.install.completed event must be exercised by clean install smoke for each promoted channel",
    ]


def test_pack12_plugin_release_artifacts_are_not_duplicated_in_monorepo_archive() -> None:
    assert not (MONOREPO_ROOT / "archive" / "extensions" / "claude-code").exists()
