"""SDK 2 compatibility contract for the local Eve MCP stdio server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

import eve_client
import eve_client.server as server


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eve_mcp_server_tools_v1.json"
SEARCH_ARGUMENTS = {"query": "SDK 2 bridge"}
SENTINEL_TEXT = "sentinel proxy result"
AUTHENTICATION_REQUIRED = "authentication_required"


def _canonical_tools(tools: list[object]) -> str:
    """Serialize the SDK 2 public tool fields in the SDK 1 fixture format."""
    payload = sorted(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "outputSchema": tool.output_schema,
            }
            for tool in tools
        ],
        key=lambda tool: tool["name"],
    )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _frozen_tools() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_in_process_client_preserves_sdk_1_tool_descriptors_and_version(mode: str) -> None:
    async with Client(server.mcp, mode=mode) as client:
        listed = await client.list_tools()

        assert _canonical_tools(listed.tools) == _frozen_tools()
        assert client.server_info.version == eve_client.__version__


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_in_process_client_forwards_memory_search_without_changing_result(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    received: list[tuple[str, dict[str, object]]] = []

    async def proxy_sentinel(tool_name: str, arguments: dict[str, object]) -> str:
        received.append((tool_name, arguments))
        return SENTINEL_TEXT

    monkeypatch.setattr(server, "_proxy", proxy_sentinel)

    async with Client(server.mcp, mode=mode) as client:
        result = await client.call_tool("memory_search", SEARCH_ARGUMENTS)

    assert received == [
        (
            "memory_search",
            {
                "query": "SDK 2 bridge",
                "context": "all",
                "store": "semantic",
                "limit": 10,
                "min_similarity": 0.7,
                "source_agent": "eve-mcp-local",
                "visibility": "PERSONAL",
            },
        )
    ]
    assert result.content[0].text == SENTINEL_TEXT


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_installed_stdio_server_preserves_sdk_1_contract_without_credentials(
    tmp_path: Path, mode: str
) -> None:
    home = tmp_path / "home"
    state_home = tmp_path / "state"
    home.mkdir()
    state_home.mkdir()
    environment = {
        "HOME": str(home),
        "XDG_STATE_HOME": str(state_home),
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        "EVE_API_KEY": "",
    }
    parameters = StdioServerParameters(
        command="eve-mcp-server",
        env=environment,
    )

    async with Client(stdio_client(parameters), mode=mode) as client:
        listed = await client.list_tools()
        result = await client.call_tool("memory_search", SEARCH_ARGUMENTS)

        assert _canonical_tools(listed.tools) == _frozen_tools()
        assert client.server_info.version == eve_client.__version__
        assert AUTHENTICATION_REQUIRED in result.content[0].text
