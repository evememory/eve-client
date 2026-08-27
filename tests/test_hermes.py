from __future__ import annotations

import os
import subprocess
import textwrap
from io import StringIO
from unittest.mock import Mock

import pytest

from eve_client.hermes import (
    HermesIntegrationError,
    _run_interactive,
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


def _interactive_process(output: str = "", returncode: int = 0) -> Mock:
    process = Mock()
    process.stdout = StringIO(output)
    process.wait.return_value = returncode
    return process


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
            _completed(
                [], stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}'
            ),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)
    popen = Mock(return_value=_interactive_process("Authenticated — eve-memory\n"))
    monkeypatch.setattr("eve_client.hermes.subprocess.Popen", popen)

    assert (
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
        == "reauthenticated"
    )
    assert popen.call_args.args[0] == [
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
            _completed(
                [], stdout="Config key not set: mcp_servers.eve-memory\n", returncode=1
            ),
            _completed(
                [], stdout='{"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}'
            ),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)
    popen = Mock(return_value=_interactive_process("Saved 'eve-memory' to profile\n"))
    monkeypatch.setattr("eve_client.hermes.subprocess.Popen", popen)

    assert connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp") == "added"
    assert popen.call_args.args[0] == [
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
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)
    popen = Mock(
        return_value=_interactive_process(
            "Connected (latency 1ms)\nTools discovered: 1\n"
        )
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.Popen", popen)

    verify_hermes_profile("team_1", "https://mcp.evemem.com/mcp")

    assert popen.call_args.args[0] == [
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
    popen = Mock(return_value=_interactive_process("Authenticated — eve-memory\n"))
    monkeypatch.setattr("eve_client.hermes.subprocess.Popen", popen)

    with pytest.raises(HermesIntegrationError, match="enabled"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")


def _fake_hermes(tmp_path):
    executable = tmp_path / "hermes"
    executable.write_text(
        textwrap.dedent(
            r"""
            #!/usr/bin/env python3
            import json
            import os
            import pathlib
            import sys

            args = sys.argv[1:]
            mode = os.environ.get("HERMES_FAKE_MODE", "")
            state_path = pathlib.Path(os.environ.get("HERMES_FAKE_STATE", ""))

            if args == ["--version"]:
                print("hermes 0.20.5")
            elif args[:3] == ["profile", "show", "team_1"]:
                print("profile team_1")
            elif "config" in args and "get" in args:
                if mode in {"add", "add-failure"} and not state_path.exists():
                    print("Config key not set: mcp_servers.eve-memory")
                    raise SystemExit(1)
                print(json.dumps({"url": "https://mcp.evemem.com/mcp", "auth": "oauth"}))
            elif "mcp" in args and "add" in args and "eve-memory" in args:
                if mode == "add-failure":
                    print("operation failed, but exit status is zero")
                else:
                    state_path.write_text("added")
                    print("Saved 'eve-memory' to profile")
            elif args[-3:] == ["mcp", "login", "eve-memory"]:
                if mode == "login-failure":
                    print("authentication failed, but exit status is zero")
                else:
                    print("Authenticated — eve-memory")
            elif args[-3:] == ["mcp", "test", "eve-memory"]:
                if mode == "test-failure":
                    print("connection failed, but exit status is zero")
                else:
                    print("Connected (latency 1ms)")
                    print("Tools discovered: 1")
            else:
                raise SystemExit(2)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _use_fake_hermes(monkeypatch, tmp_path, mode: str):
    executable = _fake_hermes(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setenv("HERMES_FAKE_MODE", mode)
    monkeypatch.setenv("HERMES_FAKE_STATE", str(tmp_path / "state"))
    return executable


def test_connect_rejects_exit_zero_add_without_success_marker(
    monkeypatch, tmp_path
) -> None:
    _use_fake_hermes(monkeypatch, tmp_path, "add-failure")

    with pytest.raises(HermesIntegrationError, match="mcp add"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")


def test_connect_accepts_exit_zero_add_with_success_marker(
    monkeypatch, tmp_path
) -> None:
    _use_fake_hermes(monkeypatch, tmp_path, "add")

    assert connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp") == "added"


def test_verify_rejects_exit_zero_test_without_success_markers(
    monkeypatch, tmp_path
) -> None:
    _use_fake_hermes(monkeypatch, tmp_path, "test-failure")

    with pytest.raises(HermesIntegrationError, match="mcp test"):
        verify_hermes_profile("team_1", "https://mcp.evemem.com/mcp")


def test_config_get_non_missing_failure_does_not_add(monkeypatch) -> None:
    run = Mock(
        side_effect=[
            _version(),
            _completed(["hermes", "profile", "show", "team_1"]),
            _completed([], stdout="permission denied", returncode=1),
        ]
    )
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )
    monkeypatch.setattr("eve_client.hermes.subprocess.run", run)

    with pytest.raises(HermesIntegrationError, match="config get"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
    assert "permission denied" not in str(run.call_args_list[-1])
    assert len(run.call_args_list) == 3


def test_connect_rejects_exit_zero_login_without_success_marker(
    monkeypatch, tmp_path
) -> None:
    _use_fake_hermes(monkeypatch, tmp_path, "login-failure")

    with pytest.raises(HermesIntegrationError, match="mcp login"):
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")


def test_connect_accepts_exit_zero_login_with_success_marker(
    monkeypatch, tmp_path
) -> None:
    _use_fake_hermes(monkeypatch, tmp_path, "login")

    assert (
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
        == "reauthenticated"
    )


def test_run_checked_converts_oserror_to_safe_error(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("secret filesystem detail")

    monkeypatch.setattr("eve_client.hermes.subprocess.run", fail)
    monkeypatch.setattr(
        "eve_client.hermes.shutil.which", lambda name: "/usr/local/bin/hermes"
    )

    with pytest.raises(HermesIntegrationError) as raised:
        connect_hermes_profile("team_1", "https://mcp.evemem.com/mcp")
    assert "secret filesystem detail" not in str(raised.value)


def test_run_interactive_converts_oserror_to_safe_error(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("secret process detail")

    monkeypatch.setattr("eve_client.hermes.subprocess.Popen", fail)

    with pytest.raises(HermesIntegrationError) as raised:
        _run_interactive(["hermes", "mcp", "test", "eve-memory"], ("Connected (",))
    assert "secret process detail" not in str(raised.value)
