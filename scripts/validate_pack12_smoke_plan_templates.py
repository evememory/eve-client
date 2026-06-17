from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS  # type: ignore[no-redef]


FIRST_WAVE_TEMPLATE_CHANNELS = {
    "claude-code-plugin": "claude-code-plugin",
    "claude-desktop": "claude-desktop",
}

SECOND_WAVE_TEMPLATE_CHANNELS = {
    "codex-plugin": "codex-plugin",
    "chatgpt-app": "chatgpt-app",
}

REMAINING_TEMPLATE_CHANNELS = {
    "install-button-cursor": "install-button-cursor",
    "install-button-vscode": "install-button-vscode",
    "gemini-cli-extension": "gemini-cli-extension",
    "cursor": "cursor",
    "vscode": "vscode",
    "windsurf": "windsurf",
}

ALL_TEMPLATE_CHANNELS = {
    **FIRST_WAVE_TEMPLATE_CHANNELS,
    **SECOND_WAVE_TEMPLATE_CHANNELS,
    **REMAINING_TEMPLATE_CHANNELS,
}

EXPECTED_RUNNER = "packages/client/scripts/run_pack12_channel_smoke.py"


@dataclass(frozen=True)
class SmokePlanTemplateValidationResult:
    ok: bool
    errors: list[str]
    template_paths: dict[str, Path]


def _string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    return None


def _validate_step(channel: str, check: str, step: object, errors: list[str]) -> None:
    if not isinstance(step, dict):
        errors.append(f"{channel} {check} must be an object")
        return
    if "command" in step:
        errors.append(f"{channel} {check} must use command_template, not command")
    if _string(step.get("purpose")) is None:
        errors.append(f"{channel} {check} purpose must be a non-empty string")
    if _string_list(step.get("command_template")) is None:
        errors.append(f"{channel} {check} command_template must be a string array")
    if _string_list(step.get("required_env")) is None:
        errors.append(f"{channel} {check} required_env must be a string array")
    if _string_list(step.get("must_contain")) is None:
        errors.append(f"{channel} {check} must_contain must be a string array")
    timeout = step.get("timeout_seconds")
    if not isinstance(timeout, int | float) or timeout <= 0:
        errors.append(f"{channel} {check} timeout_seconds must be positive")


def validate_smoke_plan_template_payload(
    payload: object,
    *,
    expected_channel: str,
) -> SmokePlanTemplateValidationResult:
    errors: list[str] = []
    template_paths: dict[str, Path] = {}
    expected_source = ALL_TEMPLATE_CHANNELS.get(expected_channel)
    if expected_source is None:
        return SmokePlanTemplateValidationResult(
            ok=False,
            errors=[f"unsupported template channel: {expected_channel}"],
            template_paths=template_paths,
        )
    if not isinstance(payload, dict):
        return SmokePlanTemplateValidationResult(
            ok=False,
            errors=[f"{expected_channel} template must be an object"],
            template_paths=template_paths,
        )

    if payload.get("pack") != "PACK-12":
        errors.append(f"{expected_channel} pack must be PACK-12")
    if payload.get("artifact") != "channel-smoke-plan-template":
        errors.append(f"{expected_channel} artifact must be channel-smoke-plan-template")
    if payload.get("channel") != expected_channel:
        errors.append(f"{expected_channel} channel must be {expected_channel}")
    if payload.get("install_source") != expected_source:
        errors.append(f"{expected_channel} install_source must be {expected_source}")
    if payload.get("proof_scope") != "actual_host_smoke":
        errors.append(f"{expected_channel} proof_scope must be actual_host_smoke")
    if payload.get("promotion_ready") is not False:
        errors.append(f"{expected_channel} template must not be promotion_ready")
    if payload.get("operator_required") is not True:
        errors.append(f"{expected_channel} operator_required must be true")
    if payload.get("runner") != EXPECTED_RUNNER:
        errors.append(f"{expected_channel} runner must be {EXPECTED_RUNNER}")
    if _string(payload.get("matrix_artifact")) is None:
        errors.append(f"{expected_channel} matrix_artifact must be a non-empty string")
    if _string(payload.get("evidence_artifact_template")) is None:
        errors.append(
            f"{expected_channel} evidence_artifact_template must be a non-empty string"
        )
    if _string_list(payload.get("not_promoted")) is None:
        errors.append(f"{expected_channel} not_promoted must be a string array")

    steps = payload.get("steps")
    if not isinstance(steps, dict):
        errors.append(f"{expected_channel} steps must be an object")
    else:
        extra_checks = sorted(set(steps) - set(REQUIRED_SMOKE_CHECKS))
        if extra_checks:
            errors.append(
                f"{expected_channel} has unknown checks: {', '.join(extra_checks)}"
            )
        for check in REQUIRED_SMOKE_CHECKS:
            if check not in steps:
                errors.append(f"{expected_channel} missing required smoke check: {check}")
                continue
            _validate_step(expected_channel, check, steps[check], errors)

    return SmokePlanTemplateValidationResult(
        ok=not errors,
        errors=errors,
        template_paths=template_paths,
    )


def _validate_smoke_plan_templates(
    templates_dir: Path,
    *,
    channels: dict[str, str],
    wave_name: str,
) -> SmokePlanTemplateValidationResult:
    errors: list[str] = []
    template_paths = {
        channel: templates_dir / f"{channel}.actual-host-template.json"
        for channel in channels
    }
    for channel, path in template_paths.items():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            errors.append(f"missing template: {path}")
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON template {path}: {exc}")
            continue
        result = validate_smoke_plan_template_payload(payload, expected_channel=channel)
        errors.extend(result.errors)

    known_template_names = {path.name for path in template_paths.values()}
    all_known_template_names = {
        f"{channel}.actual-host-template.json" for channel in ALL_TEMPLATE_CHANNELS
    }
    if templates_dir.exists():
        for path in sorted(templates_dir.glob("*.actual-host-template.json")):
            if path.name not in known_template_names and path.name not in all_known_template_names:
                errors.append(f"unexpected {wave_name} template: {path}")

    return SmokePlanTemplateValidationResult(
        ok=not errors,
        errors=errors,
        template_paths=template_paths,
    )


def validate_first_wave_smoke_plan_templates(
    templates_dir: Path,
) -> SmokePlanTemplateValidationResult:
    return _validate_smoke_plan_templates(
        templates_dir,
        channels=FIRST_WAVE_TEMPLATE_CHANNELS,
        wave_name="first-wave",
    )


def validate_second_wave_smoke_plan_templates(
    templates_dir: Path,
) -> SmokePlanTemplateValidationResult:
    return _validate_smoke_plan_templates(
        templates_dir,
        channels=SECOND_WAVE_TEMPLATE_CHANNELS,
        wave_name="second-wave",
    )


def validate_remaining_smoke_plan_templates(
    templates_dir: Path,
) -> SmokePlanTemplateValidationResult:
    return _validate_smoke_plan_templates(
        templates_dir,
        channels=REMAINING_TEMPLATE_CHANNELS,
        wave_name="remaining-channel",
    )


def main() -> int:
    templates_dir = Path(__file__).resolve().parents[1] / "smoke-plans" / "pack12"
    first_wave_result = validate_first_wave_smoke_plan_templates(templates_dir)
    second_wave_result = validate_second_wave_smoke_plan_templates(templates_dir)
    remaining_result = validate_remaining_smoke_plan_templates(templates_dir)
    errors = [
        *first_wave_result.errors,
        *second_wave_result.errors,
        *remaining_result.errors,
    ]
    if not errors:
        print("PACK-12 smoke plan templates: ok")
        return 0
    for error in errors:
        print(f"error: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
