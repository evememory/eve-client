from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _find_package_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists() and (parent / "eve_client").is_dir():
            return parent
    raise AssertionError("Could not locate eve-memory-client package root")


PACKAGE_ROOT = _find_package_root()


def test_official_hermes_loads_eve_provider_from_the_frozen_entry_point() -> None:
    hermes_source = os.environ.get("EVE_HERMES_SOURCE")
    if not hermes_source:
        pytest.skip("EVE_HERMES_SOURCE is not set; official Hermes source is required")

    script = """
from importlib.metadata import EntryPoint

from agent.memory_provider import MemoryProvider
from plugins.memory import _load_provider_from_entry_point

entry_point = EntryPoint(
    name='eve',
    value='eve_client.hermes_provider:register',
    group='hermes_agent.memory_providers',
)
provider = _load_provider_from_entry_point(entry_point, register_skills=False)
assert isinstance(provider, MemoryProvider)
assert provider.name == 'eve'
assert provider.pre_compress_checkpoint_api_version == 1
assert provider.get_tool_schemas() == []
print('ok')
"""
    env = os.environ.copy()
    pythonpath = [str(PACKAGE_ROOT), hermes_source]
    if existing_pythonpath := env.get("PYTHONPATH"):
        pythonpath.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout == "ok\n"
    assert result.stderr == ""
