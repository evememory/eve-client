"""Hermes CLI boundary for profile-scoped Eve MCP OAuth setup."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import deque
from typing import Any

MINIMUM_HERMES_VERSION = (0, 20, 5)
_PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class HermesIntegrationError(RuntimeError):
    """Raised when Hermes cannot safely configure the Eve MCP server."""


def parse_hermes_version(output: str) -> tuple[int, int, int]:
    """Parse and validate a Hermes CLI version string."""
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if match is None:
        raise HermesIntegrationError("Hermes 0.20.5 or newer is required")
    version = tuple(int(value) for value in match.groups())
    if version < MINIMUM_HERMES_VERSION:
        raise HermesIntegrationError("Hermes 0.20.5 or newer is required")
    return version


def validate_hermes_profile(profile: str | None) -> str:
    """Validate a Hermes profile name before placing it in a command argument."""
    if not isinstance(profile, str) or not _PROFILE_PATTERN.fullmatch(profile):
        raise HermesIntegrationError(
            "Hermes profile must start with a lowercase letter or number and contain only lowercase letters, numbers, underscores, or hyphens"
        )
    return profile


def _require_hermes() -> None:
    if shutil.which("hermes") is None:
        raise HermesIntegrationError("Hermes CLI is not installed or is not on PATH")
    result = _run_checked(["hermes", "--version"], capture_output=True)
    parse_hermes_version(result.stdout)


def _run_checked(
    args: list[str], *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            check=False,
            text=True,
            capture_output=capture_output,
        )
    except OSError:
        raise HermesIntegrationError(
            f"Hermes command failed: {' '.join(args)}"
        ) from None
    if result.returncode != 0:
        raise HermesIntegrationError(f"Hermes command failed: {' '.join(args)}")
    return result


def _run_interactive(
    args: list[str], required_markers: tuple[str, ...], *, all_markers: bool = True
) -> None:
    """Run an interactive Hermes command and require semantic success markers."""
    marker_window = deque(maxlen=max(map(len, required_markers)))
    markers_seen = [False] * len(required_markers)
    try:
        process = subprocess.Popen(
            args,
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if process.stdout is not None:
            while True:
                character = process.stdout.read(1)
                if not character:
                    break
                sys.stdout.write(character)
                sys.stdout.flush()
                marker_window.append(character)
                output_window = "".join(marker_window)
                for index, marker in enumerate(required_markers):
                    if marker in output_window:
                        markers_seen[index] = True
        returncode = process.wait()
    except OSError:
        raise HermesIntegrationError(
            f"Hermes command failed: {' '.join(args)}"
        ) from None

    marker_match = all(markers_seen) if all_markers else any(markers_seen)
    if returncode != 0 or not marker_match:
        raise HermesIntegrationError(f"Hermes command failed: {' '.join(args)}")


def _check_profile(profile: str) -> None:
    _run_checked(["hermes", "profile", "show", profile], capture_output=True)


def _read_mcp_entry(profile: str, server_name: str) -> dict[str, Any] | None:
    args = [
        "hermes",
        "--profile",
        profile,
        "config",
        "get",
        f"mcp_servers.{server_name}",
        "--json",
    ]
    try:
        result = subprocess.run(
            args,
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        raise HermesIntegrationError(
            f"Hermes command failed: {' '.join(args)}"
        ) from None
    if result.returncode != 0:
        combined_output = "\n".join(
            part for part in (result.stdout or "", result.stderr or "") if part
        ).strip()
        missing_diagnostic = f"Config key not set: mcp_servers.{server_name}"
        if result.returncode == 1 and combined_output == missing_diagnostic:
            return None
        raise HermesIntegrationError(f"Hermes command failed: {' '.join(args)}")
    try:
        entry = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HermesIntegrationError("Hermes returned invalid MCP server JSON") from exc
    if not isinstance(entry, dict):
        raise HermesIntegrationError("Hermes returned an invalid MCP server entry")
    return entry


def _entry_matches(entry: dict[str, Any], mcp_base_url: str) -> bool:
    return (
        entry.get("url") == mcp_base_url
        and entry.get("auth") == "oauth"
        and entry.get("enabled") is not False
    )


def _require_matching_entry(profile: str, mcp_base_url: str, server_name: str) -> None:
    entry = _read_mcp_entry(profile, server_name)
    if entry is None:
        raise HermesIntegrationError("Hermes MCP server entry is missing")
    if entry.get("enabled") is False:
        raise HermesIntegrationError("Hermes MCP server entry is not enabled")
    if entry.get("url") != mcp_base_url or entry.get("auth") != "oauth":
        raise HermesIntegrationError("Hermes MCP server entry is conflicting")


def connect_hermes_profile(
    profile: str,
    mcp_base_url: str,
    server_name: str = "eve-memory",
) -> str:
    """Add or reauthenticate the profile-scoped Eve MCP server."""
    profile = validate_hermes_profile(profile)
    _require_hermes()
    _check_profile(profile)
    entry = _read_mcp_entry(profile, server_name)

    if entry is None:
        _run_interactive(
            [
                "hermes",
                "--profile",
                profile,
                "mcp",
                "add",
                server_name,
                "--url",
                mcp_base_url,
                "--auth",
                "oauth",
            ],
            (f"Saved '{server_name}' to",),
        )
        result = "added"
    elif _entry_matches(entry, mcp_base_url):
        _run_interactive(
            ["hermes", "--profile", profile, "mcp", "login", server_name],
            ("Authenticated —", "Authenticated (server reported no tools)"),
            all_markers=False,
        )
        result = "reauthenticated"
    else:
        raise HermesIntegrationError("Hermes MCP server entry is conflicting")

    _require_matching_entry(profile, mcp_base_url, server_name)
    return result


def verify_hermes_profile(
    profile: str,
    mcp_base_url: str,
    server_name: str = "eve-memory",
) -> None:
    """Verify the configured Eve MCP server through Hermes."""
    profile = validate_hermes_profile(profile)
    _require_hermes()
    _check_profile(profile)
    _require_matching_entry(profile, mcp_base_url, server_name)
    _run_interactive(
        ["hermes", "--profile", profile, "mcp", "test", server_name],
        ("Connected (", "Tools discovered:"),
    )
