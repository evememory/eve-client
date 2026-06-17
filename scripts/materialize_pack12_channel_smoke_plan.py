from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS
    from scripts.validate_pack12_smoke_plan_templates import (
        validate_smoke_plan_template_payload,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_pack12_smoke_matrix import REQUIRED_SMOKE_CHECKS  # type: ignore[no-redef]
    from validate_pack12_smoke_plan_templates import (  # type: ignore[no-redef]
        validate_smoke_plan_template_payload,
    )


DEFAULT_EXPECTED_EXIT_CODE = 0
_SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]+|api[_-]?key\s*[:=]|token\s*[:=]|secret\s*[:=]|authorization\s*:)"
)


class SmokePlanMaterializeError(ValueError):
    """Raised when a PACK-12 smoke template cannot be materialized safely."""


@dataclass(frozen=True)
class SmokePlanMaterializeResult:
    ok: bool
    output_path: Path


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokePlanMaterializeError(f"missing {label}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokePlanMaterializeError(f"invalid JSON {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SmokePlanMaterializeError(f"{label} must be a JSON object")
    return payload


def _required_string(payload: dict[str, Any], key: str, *, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SmokePlanMaterializeError(f"{label} {key} must be a non-empty string")
    return value.strip()


def _validate_command(check: str, raw_step: object) -> list[str]:
    if not isinstance(raw_step, dict):
        raise SmokePlanMaterializeError(f"{check} command entry must be an object")
    command = raw_step.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise SmokePlanMaterializeError(f"{check} command must be a non-empty string array")
    for part in command:
        if _SECRET_PATTERN.search(part):
            raise SmokePlanMaterializeError(
                f"{check} command contains secret-like content; use environment indirection"
            )
    return command


def _materialized_step(template_step: object, command: list[str]) -> dict[str, Any]:
    if not isinstance(template_step, dict):
        raise SmokePlanMaterializeError("template step must be an object")
    must_contain = template_step.get("must_contain")
    if not isinstance(must_contain, list) or not all(
        isinstance(item, str) and item for item in must_contain
    ):
        raise SmokePlanMaterializeError("template step must_contain must be a string array")
    timeout = template_step.get("timeout_seconds")
    if not isinstance(timeout, int | float) or timeout <= 0:
        raise SmokePlanMaterializeError("template step timeout_seconds must be positive")
    return {
        "command": command,
        "timeout_seconds": timeout,
        "expected_exit_code": DEFAULT_EXPECTED_EXIT_CODE,
        "must_contain": must_contain,
    }


def materialize_smoke_plan(
    template_path: Path,
    commands_path: Path,
    output_path: Path,
) -> SmokePlanMaterializeResult:
    template = _load_json_object(template_path, label="template")
    channel = _required_string(template, "channel", label="template")
    validation = validate_smoke_plan_template_payload(template, expected_channel=channel)
    if not validation.ok:
        raise SmokePlanMaterializeError(
            "invalid smoke plan template: " + "; ".join(validation.errors)
        )

    commands = _load_json_object(commands_path, label="commands")
    target = _required_string(commands, "target", label="commands")
    clean_environment = _required_string(commands, "clean_environment", label="commands")

    raw_steps = commands.get("steps")
    if not isinstance(raw_steps, dict):
        raise SmokePlanMaterializeError("commands steps must be an object")

    template_steps = template.get("steps")
    if not isinstance(template_steps, dict):
        raise SmokePlanMaterializeError("template steps must be an object")

    materialized_steps: dict[str, dict[str, Any]] = {}
    for check in REQUIRED_SMOKE_CHECKS:
        if check not in raw_steps:
            raise SmokePlanMaterializeError(
                f"missing command for required smoke check: {check}"
            )
        materialized_steps[check] = _materialized_step(
            template_steps[check],
            _validate_command(check, raw_steps[check]),
        )

    extra_checks = sorted(set(raw_steps) - set(REQUIRED_SMOKE_CHECKS))
    if extra_checks:
        raise SmokePlanMaterializeError(
            f"unknown command checks: {', '.join(extra_checks)}"
        )

    plan = {
        "pack": "PACK-12",
        "artifact": "channel-smoke-plan",
        "schema_version": 1,
        "generated_from_template": str(template_path),
        "channel": channel,
        "install_source": template["install_source"],
        "target": target,
        "proof_scope": "actual_host_smoke",
        "clean_environment": clean_environment,
        "steps": materialized_steps,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return SmokePlanMaterializeResult(ok=True, output_path=output_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize a PACK-12 channel-smoke-plan from a reviewed template."
    )
    parser.add_argument("template", type=Path, help="Path to channel-smoke-plan-template JSON")
    parser.add_argument("commands", type=Path, help="Path to JSON with concrete commands")
    parser.add_argument("output", type=Path, help="Path to write channel-smoke-plan JSON")
    args = parser.parse_args()
    try:
        result = materialize_smoke_plan(args.template, args.commands, args.output)
    except SmokePlanMaterializeError as exc:
        print(f"error: {exc}")
        return 2
    print(f"wrote {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
