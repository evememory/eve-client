"""Bounded synchronous transport for Hermes provider memory tools."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping
from numbers import Real
from typing import Any

import httpx


_ALLOWED_TOOLS = frozenset(
    {"memory_search", "memory_pre_compact", "memory_extract", "memory_session_end"}
)
_MAX_RESPONSE_BYTES = 1_048_576
_RESPONSE_READ_CHUNK_BYTES = 64 * 1024


class EveMcpTransportError(Exception):
    """Base error for safe, typed Eve MCP transport failures."""


class EveMcpToolError(EveMcpTransportError):
    """The requested tool is outside the fixed transport allowlist."""


class EveMcpAuthenticationError(EveMcpTransportError):
    """The MCP service rejected authentication."""


class EveMcpRateLimitError(EveMcpTransportError):
    """The MCP service applied a rate limit."""


class EveMcpServerError(EveMcpTransportError):
    """The MCP service returned a server failure."""


class EveMcpNetworkError(EveMcpTransportError):
    """The MCP request timed out or could not reach the service."""


class EveMcpMalformedResponseError(EveMcpTransportError):
    """The HTTP, MCP, or tool-result response did not meet the contract."""


class EveMcpTransport:
    """Send one allowlisted JSON-RPC tool call to the hosted Eve MCP endpoint."""

    def __init__(self, endpoint: str, api_key: str, timeout: httpx.Timeout) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._timeout = timeout

    def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        timeout_override: httpx.Timeout | None = None,
    ) -> dict[str, Any]:
        """Call one allowlisted tool without retrying and return its object result."""
        if tool_name not in _ALLOWED_TOOLS:
            raise EveMcpToolError("Requested MCP tool is not allowed")
        self._validate_endpoint(self._endpoint)
        timeout = timeout_override if timeout_override is not None else self._timeout
        self._validate_timeout(timeout)

        request_body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": dict(arguments)},
        }
        headers = {
            "X-API-Key": self._api_key,
            "X-Source-Agent": "hermes_agent",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST", self._endpoint, headers=headers, json=request_body
                ) as response:
                    self._raise_for_http_status(response.status_code)
                    body = self._read_response_body(response)
        except httpx.TimeoutException:
            raise EveMcpNetworkError("MCP transport timeout") from None
        except httpx.RequestError:
            raise EveMcpNetworkError("MCP transport network failure") from None

        envelope = self._decode_envelope(body, response.headers, request_body["id"])
        return self._decode_tool_result(envelope, request_body["id"])

    @staticmethod
    def _validate_endpoint(endpoint: str) -> None:
        try:
            url = httpx.URL(endpoint)
        except (httpx.InvalidURL, TypeError, ValueError):
            raise EveMcpMalformedResponseError("Invalid MCP endpoint") from None
        if url.scheme != "https" or not url.host:
            raise EveMcpMalformedResponseError("MCP endpoint must use HTTPS")

    @staticmethod
    def _validate_timeout(timeout: httpx.Timeout) -> None:
        for value in (timeout.connect, timeout.read, timeout.write, timeout.pool):
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise EveMcpMalformedResponseError("Invalid MCP timeout")

    @staticmethod
    def _raise_for_http_status(status_code: int) -> None:
        if status_code in {401, 403}:
            raise EveMcpAuthenticationError("MCP authentication failure")
        if status_code == 429:
            raise EveMcpRateLimitError("MCP rate limit")
        if 500 <= status_code <= 599:
            raise EveMcpServerError("MCP server failure")
        if not 200 <= status_code <= 299:
            raise EveMcpMalformedResponseError("MCP request failure")

    @staticmethod
    def _read_response_body(response: httpx.Response) -> bytes:
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=_RESPONSE_READ_CHUNK_BYTES):
            if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                raise EveMcpMalformedResponseError("MCP response exceeds maximum size")
            body.extend(chunk)
        return bytes(body)

    @staticmethod
    def _decode_envelope(
        body: bytes, headers: httpx.Headers, request_id: str
    ) -> Mapping[str, Any]:
        try:
            if headers.get("content-type", "").lower().startswith("text/event-stream"):
                return EveMcpTransport._decode_sse(body.decode(), request_id)
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise EveMcpMalformedResponseError("Malformed MCP response") from None
        if not isinstance(payload, Mapping):
            raise EveMcpMalformedResponseError("Malformed MCP response")
        return payload

    @staticmethod
    def _decode_sse(body: str, request_id: str) -> Mapping[str, Any]:
        normalized_body = body.replace("\r\n", "\n").replace("\r", "\n")
        for event in normalized_body.split("\n\n"):
            data_lines = []
            for line in event.splitlines():
                if line.startswith("data:"):
                    data_line = line[5:]
                    data_lines.append(data_line[1:] if data_line.startswith(" ") else data_line)
            if not data_lines:
                continue
            data = "\n".join(data_lines)
            if not data:
                continue
            if data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                raise EveMcpMalformedResponseError("Malformed MCP SSE response") from None
            if isinstance(payload, Mapping):
                if payload.get("id") == request_id:
                    return payload
                continue
            raise EveMcpMalformedResponseError("Malformed MCP SSE response")
        raise EveMcpMalformedResponseError("Missing MCP SSE response")

    @staticmethod
    def _decode_tool_result(
        envelope: Mapping[str, Any], request_id: str
    ) -> dict[str, Any]:
        if (
            envelope.get("jsonrpc") != "2.0"
            or envelope.get("id") != request_id
            or "error" in envelope
        ):
            raise EveMcpMalformedResponseError("MCP JSON-RPC failure")
        result = envelope.get("result")
        if not isinstance(result, Mapping) or result.get("isError") is True:
            raise EveMcpMalformedResponseError("Malformed MCP tool result")

        encoded_result: Any = None
        structured_content = result.get("structuredContent")
        if isinstance(structured_content, Mapping) and "result" in structured_content:
            encoded_result = structured_content["result"]
        else:
            content = result.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, Mapping) and block.get("type") == "text":
                        encoded_result = block.get("text")
                        break
        if not isinstance(encoded_result, str):
            raise EveMcpMalformedResponseError("Missing MCP tool result")
        try:
            decoded = json.loads(encoded_result)
        except json.JSONDecodeError:
            raise EveMcpMalformedResponseError("Malformed MCP tool result") from None
        if not isinstance(decoded, dict):
            raise EveMcpMalformedResponseError("MCP tool result must be an object")
        return decoded
