from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.validate_pack12_smoke_matrix import (
        validate_remaining_smoke_matrix,
        validate_smoke_matrix,
    )
    from scripts.validate_pack12_smoke_plan_templates import (
        validate_first_wave_smoke_plan_templates,
        validate_remaining_smoke_plan_templates,
        validate_second_wave_smoke_plan_templates,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_pack12_smoke_matrix import (  # type: ignore[no-redef]
        validate_remaining_smoke_matrix,
        validate_smoke_matrix,
    )
    from validate_pack12_smoke_plan_templates import (  # type: ignore[no-redef]
        validate_first_wave_smoke_plan_templates,
        validate_remaining_smoke_plan_templates,
        validate_second_wave_smoke_plan_templates,
    )


REQUIRED_CLIENT_FILES = (
    "scripts/run_pack12_channel_smoke.py",
    "scripts/run_pack12_channel_smoke_gate.py",
    "scripts/materialize_pack12_channel_smoke_plan.py",
    "scripts/apply_pack12_channel_smoke_evidence.py",
    "scripts/validate_pack12_smoke_matrix.py",
    "scripts/validate_pack12_smoke_plan_templates.py",
    "scripts/validate_pack12_artifacts.py",
    "smoke-plans/pack12/claude-code-plugin.actual-host-template.json",
    "smoke-plans/pack12/claude-desktop.actual-host-template.json",
    "smoke-plans/pack12/codex-plugin.actual-host-template.json",
    "smoke-plans/pack12/chatgpt-app.actual-host-template.json",
    "smoke-plans/pack12/install-button-cursor.actual-host-template.json",
    "smoke-plans/pack12/install-button-vscode.actual-host-template.json",
    "smoke-plans/pack12/gemini-cli-extension.actual-host-template.json",
    "smoke-plans/pack12/cursor.actual-host-template.json",
    "smoke-plans/pack12/vscode.actual-host-template.json",
    "smoke-plans/pack12/windsurf.actual-host-template.json",
)

REQUIRED_ARTIFACTS = (
    "docs/specs/artifacts/pack12-first-wave-smoke-matrix-2026-06-17.json",
    "docs/specs/artifacts/pack12-remaining-channel-smoke-matrix-2026-06-17.json",
    "docs/specs/artifacts/pack12-channel-smoke-runner-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-smoke-matrix-updater-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-smoke-plan-materializer-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-smoke-gate-orchestrator-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-readiness-rollup-verifier-2026-06-17.json",
    "docs/specs/artifacts/pack12-first-wave-smoke-plan-templates-2026-06-17.json",
    "docs/specs/artifacts/pack12-second-wave-smoke-plan-templates-2026-06-17.json",
    "docs/specs/artifacts/pack12-remaining-channel-smoke-plan-templates-2026-06-17.json",
    "docs/specs/artifacts/pack12-channel-analytics-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-production-entrypoint-probe-2026-06-17.json",
)

PROMOTION_FALSE_ARTIFACTS = (
    "docs/specs/artifacts/pack12-channel-smoke-runner-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-smoke-matrix-updater-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-smoke-plan-materializer-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-smoke-gate-orchestrator-readiness-2026-06-17.json",
    "docs/specs/artifacts/pack12-readiness-rollup-verifier-2026-06-17.json",
    "docs/specs/artifacts/pack12-first-wave-smoke-plan-templates-2026-06-17.json",
    "docs/specs/artifacts/pack12-second-wave-smoke-plan-templates-2026-06-17.json",
    "docs/specs/artifacts/pack12-remaining-channel-smoke-plan-templates-2026-06-17.json",
    "docs/specs/artifacts/pack12-channel-analytics-readiness-2026-06-17.json",
)


@dataclass(frozen=True)
class ReadinessRollupValidationResult:
    ok: bool
    errors: list[str]


def _load_json(monorepo_root: Path, relative_path: str) -> tuple[dict[str, Any] | None, list[str]]:
    path = monorepo_root / relative_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"missing artifact: {relative_path}"]
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON artifact {relative_path}: {exc}"]
    if not isinstance(payload, dict):
        return None, [f"{relative_path} must be a JSON object"]
    return payload, []


def _validate_pack_artifact(monorepo_root: Path, relative_path: str) -> list[str]:
    payload, errors = _load_json(monorepo_root, relative_path)
    if payload is None:
        return errors
    if payload.get("pack") != "PACK-12":
        errors.append(f"{relative_path} pack must be PACK-12")
    return errors


def _validate_readiness_artifact(monorepo_root: Path, relative_path: str) -> list[str]:
    payload, errors = _load_json(monorepo_root, relative_path)
    if payload is None:
        return errors
    if payload.get("pack") != "PACK-12":
        errors.append(f"{relative_path} pack must be PACK-12")
    if payload.get("promotion_ready") is not False:
        errors.append(f"{relative_path} promotion_ready must be false")
    return errors


def _validate_required_client_files(client_root: Path) -> list[str]:
    return [
        f"missing client file: {relative_path}"
        for relative_path in REQUIRED_CLIENT_FILES
        if not (client_root / relative_path).is_file()
    ]


def validate_pack12_readiness_rollup(
    client_root: Path,
    monorepo_root: Path,
) -> ReadinessRollupValidationResult:
    errors: list[str] = []
    errors.extend(_validate_required_client_files(client_root))

    for relative_path in REQUIRED_ARTIFACTS:
        errors.extend(_validate_pack_artifact(monorepo_root, relative_path))
    for relative_path in PROMOTION_FALSE_ARTIFACTS:
        errors.extend(_validate_readiness_artifact(monorepo_root, relative_path))

    first_wave_matrix = (
        monorepo_root
        / "docs/specs/artifacts/pack12-first-wave-smoke-matrix-2026-06-17.json"
    )
    remaining_matrix = (
        monorepo_root
        / "docs/specs/artifacts/pack12-remaining-channel-smoke-matrix-2026-06-17.json"
    )
    first_wave_result = validate_smoke_matrix(first_wave_matrix)
    remaining_result = validate_remaining_smoke_matrix(remaining_matrix)
    errors.extend(f"first-wave smoke matrix: {error}" for error in first_wave_result.errors)
    errors.extend(f"remaining smoke matrix: {error}" for error in remaining_result.errors)

    templates_dir = client_root / "smoke-plans" / "pack12"
    first_templates = validate_first_wave_smoke_plan_templates(templates_dir)
    second_templates = validate_second_wave_smoke_plan_templates(templates_dir)
    remaining_templates = validate_remaining_smoke_plan_templates(templates_dir)
    errors.extend(f"first-wave smoke templates: {error}" for error in first_templates.errors)
    errors.extend(f"second-wave smoke templates: {error}" for error in second_templates.errors)
    errors.extend(f"remaining smoke templates: {error}" for error in remaining_templates.errors)

    return ReadinessRollupValidationResult(ok=not errors, errors=errors)


def main() -> int:
    default_client_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Validate the PACK-12 readiness rollup artifacts and smoke gates."
    )
    parser.add_argument(
        "--client-root",
        type=Path,
        default=default_client_root,
        help="Path to the eve-client/package root",
    )
    parser.add_argument(
        "--monorepo-root",
        type=Path,
        default=default_client_root.parents[1],
        help="Path to the Eve monorepo root",
    )
    args = parser.parse_args()
    result = validate_pack12_readiness_rollup(args.client_root, args.monorepo_root)
    if result.ok:
        print("PACK-12 readiness rollup: ok")
        return 0
    for error in result.errors:
        print(f"error: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
