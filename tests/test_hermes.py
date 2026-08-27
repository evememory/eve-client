from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest

from eve_client.hermes import (
    HermesIntegrationError,
    connect_hermes_profile,
    parse_hermes_version,
    validate_hermes_profile,
    verify_hermes_profile,
)


def _completed(
    args: list[str], *, stdout: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")


def _version() -> subprocess.CompletedProcess[str]:
    return _completed(["hermes", "--version"], stdout="hermes 0.20.5\n")


def test_parse_hermes_version_accepts_required_version() -> None:
    assert parse_hermes_version("hermes 0.20.5\n") == (0, 20, 5)


@pytest.mark.parametrize("output", ["hermes 0.20.4", "hermes version 1.0", "unknown"])
def test_parse_hermes_version_rejects_older_or_malformed_versions(output: str) -> None:
    with pytest.raises(HermesIntegrationError, match="Hermes 0.20.5 or newer"):
        parse_hermes_version(output)


@pytest.mark.parametrize(
    "profile",
    [
        None,
        "",
        " team_1",
        "team_1 ",
        "team/1",
        "Team_1",
        "_team_1",
        "1" * 65,
    ],
)
def test_validate_hermes_profile_rejects_missing_or_malformed_values(
    profile: str | None,
) -> None:
    with pytest.raises(HermesIntegrationError, match="profile"):
        validate_hermes_profile(profile)


def test_validate_hermes_profile_accepts_team_1() -> None:
    assert validate_hermes_profile("team_1") == "team_1"


def test_connect_rejects_older_hermes_before_profile_inspection(monkeypatch) -> None:
    run = Mock(side_effect=[_completed([], stdout="hermes 0.20.4\n")])
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    with pytest.raises(HermesIntegrationError, match="Hermes 0.20.5 or newer"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
    assert [call.args[0] for call in run.call_args_list] == [["hermes", "--version"]]


def test_verify_rejects_older_hermes_before_profile_inspection(monkeypatch) -> None:
    run = Mock(side_effect=[_completed([], stdout="hermes 0.20.4\n")])
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    with pytest.raises(HermesIntegrationError, match="Hermes 0.20.5 or newer"):
        verify_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
    assert [call.args[0] for call in run.call_args_list] == [["hermes", "--version"]]


def test_connect_reauthenticates_matching_existing_entry(monkeypatch) -> None:
    run = Mock(
        side_effect=[
            _version(),
            _completed(["hermes", "profile", "show", "team_1"]),
            _completed(
                [], stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}'
            ),
            _completed(["hermes", "--profile", "team_1", "mcp", "login", "eve-memory"]),
            _completed(
                [], stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}'
            ),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    assert (
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
        == "reauthenticated"
    )
    assert run.call_args_list[3].args[0] == [
        "hermes",
        "--profile",
        "team_1",
        "mcp",
        "login",
        "eve-memory",
    ]


def test_connect_adds_missing_entry(monkeypatch) -> None:
    run = Mock(
        side_effect=[
            _version(),
            _completed(["hermes", "profile", "show", "team_1"]),
            _completed([], returncode=1),
            _completed([]),
            _completed(
                [], stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}'
            ),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    assert connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp") == "added"
    assert run.call_args_list[3].args[0] == [
        "hermes",
        "--profile",
        "team_1",
        "mcp",
        "add",
        "eve-memory",
        "--url",
        "https://mcp.evemem.com/mcp",
        "--auth",
        "oauth",
    ]


def test_connect_rejects_conflicting_entry_without_mutation(monkeypatch) -> None:
    run = Mock(
        side_effect=[
            _version(),
            _completed(["hermes", "profile", "show", "team_1"]),
            _completed(
                [], stdout='{"url": "https://other.example/mcp", "auth": "oauth"}'
            ),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    with pytest.raises(HermesIntegrationError, match="conflicting"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
    assert [call.args[0] for call in run.call_args_list] == [
        ["hermes", "--version"],
        ["hermes", "profile", "show", "team_1"],
        [
            "hermes",
            "--profile",
            "team_1",
            "config",
            "get",
            "mcp_servers.eve-memory",
            "--json",
        ],
    ]


def test_verify_runs_profile_scoped_test(monkeypatch) -> None:
    run = Mock(
        side_effect=[
            _version(),
            _completed(["hermes", "profile", "show", "team_1"]),
            _completed(
                [],
                stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth", "enabled": true}',
            ),
            _completed([]),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    verify_hermes_profile("team_1", "https://mcp.evemem.com/mcp")

    assert run.call_args_list[3].args[0] == [
        "hermes",
        "--profile",
        "team_1",
        "mcp",
        "test",
        "eve-memory",
    ]


def test_connect_rejects_entry_disabled_after_login(monkeypatch) -> None:
    run = Mock(
        side_effect=[
            _version(),
            _completed(["hermes", "profile", "show", "team_1"]),
            _completed(
                [], stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}'
            ),
            _completed([]),
            _completed(
                [],
                stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth", "enabled": false}',
            ),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    with pytest.raises(HermesIntegrationError, match="enabled"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
