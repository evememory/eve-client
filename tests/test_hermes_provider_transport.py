"""Contract tests for the bounded Hermes-to-Eve MCP transport."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from eve_client.hermes_provider.transport import (
    EveMcpMalformedResponseError,
    EveMcpTransport,
    EveMcpTransportError,
)


FIXTURES = Path(__file__).parent / "fixtures" / "hermes_provider_mcp"
API_KEY = "secret-api-key"
REQUEST_CONTENT = "private request transcript"
RESPONSE_CONTENT = "private response transcript"
ResponseFactory = Callable[[dict[str, Any]], httpx.Response]
MAX_RESPONSE_BYTES = 1_048_576


class RecordingClient:
    """Deterministic replacement for the external HTTP boundary."""

    def __init__(self, *, timeout: httpx.Timeout) -> None:
        self.timeout = timeout
        self.requests: list[dict[str, Any]] = []
        self.response: httpx.Response | Exception | ResponseFactory = httpx.Response(500)

    def __enter__(self) -> RecordingClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: Any) -> RecordingResponseStream:
        self.requests.append({"method": method, "url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        if callable(self.response):
            return RecordingResponseStream(self.response(kwargs["json"]))
        return RecordingResponseStream(self.response)


class RecordingResponseStream:
    """Small context-manager shape returned by ``httpx.Client.stream``."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def __enter__(self) -> httpx.Response:
        return self.response

    def __exit__(self, *args: object) -> None:
        self.response.close()


class FailingByteStream(httpx.SyncByteStream):
    """Raise a transport error while a response body is being consumed."""

    def __init__(self, error: httpx.RequestError) -> None:
        self.error = error

    def __iter__(self) -> Any:
        raise self.error
        yield b""

    def close(self) -> None:
        return None


def successful_response(name: str = "memory-search-success.json") -> ResponseFactory:
    envelope = json.loads((FIXTURES / name).read_text())

    def respond(request: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json={**envelope, "id": request["id"]})

    return respond


def response_with_request_id(response: httpx.Response) -> ResponseFactory:
    envelope = response.json()

    def respond(request: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            json={**envelope, "id": request["id"]},
        )

    return respond


def transport(
    endpoint: str = "https://memory.example/mcp", timeout: httpx.Timeout | None = None
) -> EveMcpTransport:
    return EveMcpTransport(
        endpoint=endpoint,
        api_key=API_KEY,
        timeout=timeout or httpx.Timeout(7.5),
    )


def sized_successful_response(size: int, *, content_length: str | None = None) -> ResponseFactory:
    """Return a valid envelope with an exact encoded response size."""

    def respond(request: dict[str, Any]) -> httpx.Response:
        payload = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "structuredContent": {"result": '{"results":[]}'},
                "isError": False,
            },
            "padding": "",
        }
        encoded = json.dumps(payload).encode()
        payload["padding"] = "x" * (size - len(encoded))
        content = json.dumps(payload).encode()
        assert len(content) == size
        headers = {} if content_length is None else {"content-length": content_length}
        return httpx.Response(200, headers=headers, content=content)

    return respond


def test_posts_exact_json_rpc_request_headers_timeout_and_unique_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: a wrong MCP method/body/header, lost timeout, or reused request ID.
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = successful_response()
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    client = transport()

    assert client.call_tool("memory_search", {"query": REQUEST_CONTENT}) == {"results": []}
    assert client.call_tool("memory_search", {"query": REQUEST_CONTENT}) == {"results": []}

    assert len(clients) == 2
    assert all(recording.timeout == httpx.Timeout(7.5) for recording in clients)
    requests = [recording.requests[0] for recording in clients]
    assert all(request["url"] == "https://memory.example/mcp" for request in requests)
    assert all(request["headers"] == {
        "X-API-Key": API_KEY,
        "X-Source-Agent": "hermes_agent",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    } for request in requests)
    assert all(request["json"]["jsonrpc"] == "2.0" for request in requests)
    assert all(request["json"]["method"] == "tools/call" for request in requests)
    assert all(request["json"]["params"] == {
        "name": "memory_search", "arguments": {"query": REQUEST_CONTENT}
    } for request in requests)
    assert requests[0]["json"]["id"] != requests[1]["json"]["id"]


def test_uses_valid_per_call_timeout_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: a lifecycle caller cannot shorten one bounded request below its configured timeout.
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = successful_response()
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)

    assert transport(timeout=httpx.Timeout(15)).call_tool(
        "memory_search", {}, timeout_override=httpx.Timeout(2)
    ) == {"results": []}
    assert clients[0].timeout == httpx.Timeout(2)


def test_rejects_a_streamed_response_larger_than_the_fixed_limit_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: a response body can be buffered without a fixed transport limit.
    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = sized_successful_response(
            MAX_RESPONSE_BYTES + 1, content_length="1"
        )
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    monkeypatch.setattr(
        EveMcpTransport,
        "_decode_envelope",
        lambda *args: (_ for _ in ()).throw(AssertionError("response must not be parsed")),
    )
    with pytest.raises(EveMcpMalformedResponseError, match="MCP response exceeds maximum size"):
        transport().call_tool("memory_search", {})


def test_accepts_a_response_at_the_fixed_limit_even_when_content_length_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: content-length is used as the only size check or exact-limit data is rejected.
    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = sized_successful_response(
            MAX_RESPONSE_BYTES, content_length=str(MAX_RESPONSE_BYTES + 1)
        )
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    assert transport().call_tool("memory_search", {}) == {"results": []}


@pytest.mark.parametrize("timeout_override", [httpx.Timeout(None), httpx.Timeout(2, read=0)])
def test_rejects_invalid_per_call_timeout_override_before_opening_network_client(
    monkeypatch: pytest.MonkeyPatch, timeout_override: httpx.Timeout
) -> None:
    # Break caught: an invalid lifecycle timeout override can open a network client.
    def no_client(**kwargs: Any) -> RecordingClient:
        raise AssertionError("network client must not be opened")

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", no_client)
    with pytest.raises(EveMcpMalformedResponseError):
        transport().call_tool("memory_search", {}, timeout_override=timeout_override)


@pytest.mark.parametrize(
    ("tool_name", "fixture_name", "expected"),
    [
        ("memory_search", "memory-search-success.json", {"results": []}),
        ("memory_pre_compact", "memory-pre-compact-success.json", {"status": "success", "chunk_id": "00000000-0000-0000-0000-000000000000", "returned_ids": ["00000000-0000-0000-0000-000000000000"]}),
        ("memory_extract", "memory-extract-success.json", {"extracted_count": 0, "stored_count": 0, "zero_result_reason": "No extracted items met durability or importance requirements.", "items": [], "store_results": None}),
        ("memory_session_end", "memory-session-end-success.json", {"status": "success", "entry_id": "00000000-0000-0000-0000-000000000000", "session_id": "00000000-0000-0000-0000-000000000000", "context": "personal"}),
    ],
)
def test_decodes_each_allowlisted_tool_success_fixture(
    monkeypatch: pytest.MonkeyPatch, tool_name: str, fixture_name: str, expected: dict[str, Any]
) -> None:
    # Break caught: an allowlisted tool cannot decode its hosted response shape.
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = successful_response(fixture_name)
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    assert transport().call_tool(tool_name, {}) == expected
    assert clients[0].requests[0]["json"]["params"]["name"] == tool_name


def test_rejects_unknown_tool_before_opening_network_client(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: arbitrary tool names are sent over the network.
    def no_client(**kwargs: Any) -> RecordingClient:
        raise AssertionError("network client must not be opened")

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", no_client)
    with pytest.raises(EveMcpTransportError):
        transport().call_tool("memory_store", {"secret": REQUEST_CONTENT})


@pytest.mark.parametrize("endpoint", ["http://memory.example/mcp", "ftp://memory.example/mcp"])
def test_rejects_non_https_endpoint_before_opening_network_client(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    # Break caught: credentials can be sent over a non-TLS connection.
    def no_client(**kwargs: Any) -> RecordingClient:
        raise AssertionError("network client must not be opened")

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", no_client)
    with pytest.raises(EveMcpMalformedResponseError):
        transport(endpoint).call_tool("memory_search", {})


@pytest.mark.parametrize(
    "timeout",
    [
        httpx.Timeout(None),
        httpx.Timeout(5, connect=0),
        httpx.Timeout(5, read=-1),
        httpx.Timeout(5, write=float("inf")),
        httpx.Timeout(5, pool=float("inf")),
    ],
)
def test_rejects_unbounded_or_invalid_timeout_before_opening_network_client(
    monkeypatch: pytest.MonkeyPatch, timeout: httpx.Timeout
) -> None:
    # Break caught: a bounded transport opens a client with an unsafe timeout component.
    def no_client(**kwargs: Any) -> RecordingClient:
        raise AssertionError("network client must not be opened")

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", no_client)
    with pytest.raises(EveMcpMalformedResponseError) as raised:
        transport(timeout=timeout).call_tool("memory_search", {"query": REQUEST_CONTENT})
    message = str(raised.value)
    assert API_KEY not in message
    assert REQUEST_CONTENT not in message
    assert "inf" not in message.lower()


def test_decodes_sse_envelope_and_text_content_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: SSE or text-only hosted responses are not decoded.
    envelope = {
        "jsonrpc": "2.0",
        "id": "sse-id",
        "result": {"content": [{"type": "text", "text": '{"from":"sse"}'}], "isError": False},
    }
    def response(request: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=(
                ": keepalive\n\ndata: "
                + json.dumps({**envelope, "id": request["id"]})
                + "\n\ndata: [DONE]\n\n"
            ),
        )
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = response
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    assert transport().call_tool("memory_search", {}) == {"from": "sse"}


def test_scans_crlf_sse_events_until_the_matching_response(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: an SSE notification or another request's response ends this request.
    def response(request: dict[str, Any]) -> httpx.Response:
        notification = {"jsonrpc": "2.0", "method": "notifications/progress"}
        other_response = {
            "jsonrpc": "2.0",
            "id": "other-request",
            "result": {"structuredContent": {"result": '{"wrong":true}'}, "isError": False},
        }
        matching_response = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"structuredContent": {"result": '{"matching":true}'}, "isError": False},
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=(
                ": keepalive\r\n\r\n"
                + "data: " + json.dumps(notification) + "\r\n\r\n"
                + "data: " + json.dumps(other_response) + "\r\n\r\n"
                + "data: " + json.dumps(matching_response) + "\r\r"
            ),
        )

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = response
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    assert transport().call_tool("memory_search", {}) == {"matching": True}


def test_sse_skips_empty_data_but_preserves_additional_leading_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: blank SSE data blocks a result, or extra payload whitespace becomes [DONE].
    def matching_response(request: dict[str, Any]) -> str:
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "structuredContent": {"result": '{"matching":true}'},
                    "isError": False,
                },
            }
        )

    def empty_data_then_match(request: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: \n\ndata: " + matching_response(request) + "\n\n",
        )

    def extra_space_before_done(request: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data:  [DONE]\n\ndata: " + matching_response(request) + "\n\n",
        )

    responses = iter([empty_data_then_match, extra_space_before_done])

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = next(responses)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    assert transport().call_tool("memory_search", {}) == {"matching": True}
    with pytest.raises(EveMcpMalformedResponseError):
        transport().call_tool("memory_search", {})


@pytest.mark.parametrize("is_sse", [False, True])
@pytest.mark.parametrize("response_id", [None, "different-response-id"])
def test_rejects_missing_or_mismatched_response_id_for_json_and_sse(
    monkeypatch: pytest.MonkeyPatch, is_sse: bool, response_id: str | None
) -> None:
    # Break caught: a response for a different request is accepted as this request's result.
    envelope = {
        "jsonrpc": "2.0",
        "result": {"structuredContent": {"result": '{"safe":true}'}, "isError": False},
    }

    def response(request: dict[str, Any]) -> httpx.Response:
        payload = {**envelope}
        if response_id is not None:
            payload["id"] = response_id
        if is_sse:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text="data: " + json.dumps(payload) + "\n\n",
            )
        return httpx.Response(200, json=payload)

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = response
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpMalformedResponseError) as raised:
        transport().call_tool("memory_search", {"query": REQUEST_CONTENT})
    assert API_KEY not in str(raised.value)
    assert REQUEST_CONTENT not in str(raised.value)
    assert RESPONSE_CONTENT not in str(raised.value)


@pytest.mark.parametrize(
    ("status", "expected_type"),
    [(401, "authentication"), (403, "authentication"), (429, "rate limit"), (400, "request"), (500, "server")],
)
def test_maps_http_failures_to_safe_typed_transport_errors(
    monkeypatch: pytest.MonkeyPatch, status: int, expected_type: str
) -> None:
    # Break caught: HTTP failure class is hidden or unsafe response data leaks.
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = httpx.Response(status, text=RESPONSE_CONTENT)
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpTransportError) as raised:
        transport().call_tool("memory_search", {"query": REQUEST_CONTENT})
    message = str(raised.value).lower()
    assert expected_type in message
    assert API_KEY not in message
    assert REQUEST_CONTENT not in message
    assert RESPONSE_CONTENT not in message


@pytest.mark.parametrize("error", [httpx.TimeoutException("timeout " + RESPONSE_CONTENT), httpx.NetworkError("network " + RESPONSE_CONTENT)])
def test_maps_timeout_and_network_errors_without_sensitive_text(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    # Break caught: network failure leaks upstream exception or request data.
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = error
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpTransportError) as raised:
        transport().call_tool("memory_search", {"query": REQUEST_CONTENT})
    assert "transport" in str(raised.value).lower()
    assert RESPONSE_CONTENT not in str(raised.value)
    assert REQUEST_CONTENT not in str(raised.value)
    assert API_KEY not in str(raised.value)


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (httpx.TimeoutException("timeout " + RESPONSE_CONTENT), "MCP transport timeout"),
        (httpx.NetworkError("network " + RESPONSE_CONTENT), "MCP transport network failure"),
    ],
)
def test_maps_streamed_timeout_and_network_errors_without_sensitive_text(
    monkeypatch: pytest.MonkeyPatch, error: httpx.RequestError, expected_message: str
) -> None:
    # Break caught: a response-stream error leaks upstream data or bypasses typed error mapping.
    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = httpx.Response(200, stream=FailingByteStream(error))
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpTransportError, match=expected_message) as raised:
        transport().call_tool("memory_search", {"query": REQUEST_CONTENT})
    assert RESPONSE_CONTENT not in str(raised.value)
    assert REQUEST_CONTENT not in str(raised.value)
    assert API_KEY not in str(raised.value)


def test_sanitized_traceback_omits_sensitive_network_error_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: a safe exception message still leaks the original failure traceback.
    original_error = httpx.NetworkError(
        "network " + API_KEY + " " + REQUEST_CONTENT + " " + RESPONSE_CONTENT
    )

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = original_error
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpTransportError) as raised:
        transport().call_tool("memory_search", {"query": REQUEST_CONTENT})
    formatted = "".join(traceback.format_exception(raised.value))
    assert API_KEY not in formatted
    assert REQUEST_CONTENT not in formatted
    assert RESPONSE_CONTENT not in formatted


def test_rejects_top_level_valid_json_non_object_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: valid JSON arrays are treated as MCP JSON-RPC envelopes.
    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = httpx.Response(200, json=[])
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpMalformedResponseError, match="Malformed MCP response"):
        transport().call_tool("memory_search", {})


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json " + RESPONSE_CONTENT),
        httpx.Response(200, headers={"content-type": "text/event-stream"}, text="data: not-json\n\n"),
        response_with_request_id(httpx.Response(200, json={"jsonrpc": "2.0", "error": {"message": RESPONSE_CONTENT}})),
        response_with_request_id(httpx.Response(200, json={"jsonrpc": "2.0", "result": {"isError": True}})),
        response_with_request_id(httpx.Response(200, json={"jsonrpc": "2.0"})),
        response_with_request_id(httpx.Response(200, json={"jsonrpc": "2.0", "result": {"content": []}})),
        response_with_request_id(httpx.Response(200, json={"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "not-json"}]}})),
        response_with_request_id(httpx.Response(200, json={"jsonrpc": "2.0", "result": {"structuredContent": {"result": "[]"}}})),
    ],
)
def test_rejects_malformed_mcp_results_without_sensitive_data(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response | ResponseFactory
) -> None:
    # Break caught: malformed MCP data becomes a false successful tool result.
    clients: list[RecordingClient] = []

    def make_client(*, timeout: httpx.Timeout) -> RecordingClient:
        client = RecordingClient(timeout=timeout)
        client.response = response
        clients.append(client)
        return client

    monkeypatch.setattr("eve_client.hermes_provider.transport.httpx.Client", make_client)
    with pytest.raises(EveMcpTransportError) as raised:
        transport().call_tool("memory_search", {"query": REQUEST_CONTENT})
    assert REQUEST_CONTENT not in str(raised.value)
    assert RESPONSE_CONTENT not in str(raised.value)
    assert API_KEY not in str(raised.value)
