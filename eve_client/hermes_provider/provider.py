"""Foundation for the Hermes-native Eve memory provider."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from agent.memory_provider import MemoryProvider
from agent.secret_scope import get_secret

from eve_client.atomic import atomic_write
from eve_client.hermes_provider.transport import EveMcpTransport

_ENDPOINT = "https://mcp.evemem.com/mcp"
_CONFIG_FILE = "eve.json"
_DEFAULT_CONFIG = {
    "context": "personal",
    "auto_recall": True,
    "recall_limit": 5,
    "min_similarity": 0.7,
    "request_timeout_seconds": 5,
    "session_end_timeout_seconds": 20,
}
_CONFIG_KEYS = frozenset(_DEFAULT_CONFIG)
_INTEGER_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_DECIMAL_TEXT = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_MAX_QUERY_CHARS = 2_000
_RECALL_CACHE_SECONDS = 300
_MAX_RECALL_BYTES = 8_192
_MAX_MESSAGE_BYTES = 4_096
_MAX_BUFFER_TURNS = 20
_MAX_BUFFER_MESSAGES = 40
_MAX_BUFFER_BYTES = 32_768
_MAX_SESSION_TRANSCRIPT_BYTES = (
    _MAX_BUFFER_BYTES
    + _MAX_BUFFER_TURNS * (len("User: ") + len("Assistant: "))
    + (_MAX_BUFFER_MESSAGES - 1)
)
_ENDED_SESSION_LIMIT = 100
_SESSION_END_JOIN_MARGIN_SECONDS = 1.0
_LOGGER = logging.getLogger(__name__)


def _session_end_join_seconds(operation_timeout_seconds: float) -> float:
    return operation_timeout_seconds * 2 + _SESSION_END_JOIN_MARGIN_SECONDS


def _truncate_utf8(value: str, maximum: int) -> str:
    """Return value limited to maximum UTF-8 bytes without splitting a character."""
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value
    return encoded[:maximum].decode("utf-8", errors="ignore")


def _normalized_text(value: str, maximum: int) -> str:
    return _truncate_utf8(" ".join(value.split()), maximum)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, Mapping) or block.get("type") not in {
            "text", "input_text", "output_text"
        }:
            continue
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return " ".join(parts)


def _transcript_from_turns(turns: list[tuple[str, str]]) -> str:
    return "\n".join(
        line
        for user, assistant in turns
        for line in (f"User: {user}", f"Assistant: {assistant}")
    )


def _buffer_content_bytes(turns: deque[tuple[str, str]]) -> int:
    return sum(len(value.encode("utf-8")) for turn in turns for value in turn)


def _normalize_setup_values(values: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(values)
    for key in _CONFIG_KEYS:
        value = normalized.get(key)
        if not isinstance(value, str) or key == "context":
            continue
        if key == "auto_recall":
            lowered = value.lower()
            if lowered not in {"true", "false"}:
                raise ValueError("Invalid Eve configuration")
            normalized[key] = lowered == "true"
        elif key == "recall_limit":
            if not _INTEGER_TEXT.fullmatch(value):
                raise ValueError("Invalid Eve configuration")
            normalized[key] = int(value, 10)
        elif key in {
            "min_similarity",
            "request_timeout_seconds",
            "session_end_timeout_seconds",
        }:
            if not _DECIMAL_TEXT.fullmatch(value):
                raise ValueError("Invalid Eve configuration")
            normalized[key] = float(value)
    return normalized


def _is_valid_api_key(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_config(values: Mapping[str, Any]) -> dict[str, Any]:
    config = dict(_DEFAULT_CONFIG)
    recognized = {key: value for key, value in values.items() if key in _CONFIG_KEYS}
    config.update(recognized)

    if not isinstance(config["context"], str) or not config["context"].strip():
        raise ValueError("Invalid Eve configuration")
    if not isinstance(config["auto_recall"], bool):
        raise ValueError("Invalid Eve configuration")
    if (
        isinstance(config["recall_limit"], bool)
        or not isinstance(config["recall_limit"], int)
        or not 1 <= config["recall_limit"] <= 20
    ):
        raise ValueError("Invalid Eve configuration")
    for key, lower, upper in (
        ("min_similarity", 0, 1),
        ("request_timeout_seconds", 1, 15),
        ("session_end_timeout_seconds", 5, 30),
    ):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lower <= value <= upper:
            raise ValueError("Invalid Eve configuration")
    return config


def _read_config(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("Invalid Eve configuration") from None
    if not isinstance(raw, Mapping):
        raise ValueError("Invalid Eve configuration")
    return raw


def _load_config(hermes_home: str) -> dict[str, Any]:
    path = Path(hermes_home) / _CONFIG_FILE
    if not path.exists():
        return dict(_DEFAULT_CONFIG)
    return _validate_config(_read_config(path))


class EveMemoryProvider(MemoryProvider):
    """Hermes lifecycle adapter for bounded Eve memory operations."""

    pre_compress_checkpoint_api_version = 1

    def __init__(self) -> None:
        self._active = False
        self._transport: EveMcpTransport | None = None
        self._session_id = ""
        self._platform = ""
        self._agent_identity = ""
        self._agent_workspace = ""
        self._parent_session_id = ""
        self._config = dict(_DEFAULT_CONFIG)
        self._state_lock = threading.Lock()
        self._generation = 0
        self._recall_cache: tuple[str, int, float, bool] | None = None
        self._recall_text = ""
        self._turn_buffer: deque[tuple[str, str]] = deque()
        self._ended_session_ids: deque[str] = deque(maxlen=_ENDED_SESSION_LIMIT)
        self._session_end_worker: threading.Thread | None = None

    @property
    def name(self) -> str:
        return "eve"

    def is_available(self) -> bool:
        return _is_valid_api_key(get_secret("EVE_API_KEY", ""))

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return []

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "api_key", "description": "Eve API key", "secret": True, "required": True, "env_var": "EVE_API_KEY", "url": "https://evemem.com/app"},
            {"key": "context", "description": "Eve memory context", "type": "text", "default": "personal"},
            {"key": "auto_recall", "description": "Enable automatic Eve recall", "type": "boolean", "default": True},
            {"key": "recall_limit", "description": "Maximum recalled memories", "type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            {"key": "min_similarity", "description": "Minimum recall similarity", "type": "number", "default": 0.7, "minimum": 0, "maximum": 1},
            {"key": "request_timeout_seconds", "description": "Eve request timeout in seconds", "type": "number", "default": 5, "minimum": 1, "maximum": 15},
            {"key": "session_end_timeout_seconds", "description": "Eve session-end timeout in seconds", "type": "number", "default": 20, "minimum": 5, "maximum": 30},
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        if not isinstance(values, Mapping):
            raise ValueError("Invalid Eve configuration")
        normalized_values = _normalize_setup_values(values)
        path = Path(hermes_home) / _CONFIG_FILE
        existing = _read_config(path) if path.exists() else {}
        _validate_config(existing)
        update = {key: value for key, value in normalized_values.items() if key in _CONFIG_KEYS}
        merged = {**existing, **update}
        _validate_config(merged)
        persisted = {
            key: merged[key]
            for key in _CONFIG_KEYS
            if key in existing or key in update
        }
        atomic_write(path, json.dumps(persisted, sort_keys=True) + "\n", permissions=0o600)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self.shutdown()
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("A Hermes session ID is required")
        if kwargs.get("agent_context", "primary") != "primary":
            return

        hermes_home = kwargs.get("hermes_home")
        if not isinstance(hermes_home, str) or not hermes_home:
            raise ValueError("A Hermes profile directory is required")
        config = _load_config(hermes_home)
        api_key = get_secret("EVE_API_KEY", "")
        if not _is_valid_api_key(api_key):
            raise ValueError("Eve API key is required")
        timeout_seconds = config["request_timeout_seconds"]
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=timeout_seconds,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=timeout_seconds,
        )
        with self._state_lock:
            self._transport = EveMcpTransport(_ENDPOINT, api_key, timeout)
            self._active = True
            self._config = config
            self._session_id = session_id
            self._platform = kwargs.get("platform", "")
            self._agent_identity = kwargs.get("agent_identity", "")
            self._agent_workspace = kwargs.get("agent_workspace", "")
            self._parent_session_id = kwargs.get("parent_session_id", "")

    def shutdown(self) -> None:
        with self._state_lock:
            self._generation += 1
            self._active = False
            self._transport = None
            self._session_id = ""
            self._platform = ""
            self._agent_identity = ""
            self._agent_workspace = ""
            self._parent_session_id = ""
            self._recall_cache = None
            self._recall_text = ""
            self._turn_buffer.clear()

    def on_session_switch(
        self, session_id: str, parent_session_id: str = "", **kwargs: Any
    ) -> None:
        """Isolate state when Hermes changes the active conversation lineage."""
        parent = kwargs.get("parent_session_id", parent_session_id)
        if not isinstance(parent, str):
            parent = ""
        with self._state_lock:
            self._generation += 1
            self._session_id = session_id
            self._parent_session_id = parent
            self._recall_cache = None
            self._recall_text = ""
            self._turn_buffer.clear()

    def queue_prefetch(self, query: str, session_id: str = "") -> None:
        """Fetch one bounded recall entry, subject to current session state."""
        if not isinstance(query, str) or not query:
            return
        with self._state_lock:
            if (
                not self._active
                or not self._session_id
                or not self._config["auto_recall"]
                or self._transport is None
                or (session_id and session_id != self._session_id)
            ):
                return
            current_session = self._session_id
            generation = self._generation
            transport = self._transport
            config = dict(self._config)
        bounded_query = query[:_MAX_QUERY_CHARS]
        try:
            result = transport.call_tool(
                "memory_search",
                {
                    "query": bounded_query,
                    "source_agent": "hermes_agent",
                    "context": config["context"],
                    "store": "all",
                    "limit": config["recall_limit"],
                    "min_similarity": config["min_similarity"],
                },
            )
            formatted = self._format_recall(result)
        except Exception:
            _LOGGER.warning("Eve Hermes recall failed")
            formatted = ""
        with self._state_lock:
            if not (
                self._active
                and self._session_id == current_session
                and self._generation == generation
            ):
                return
            if formatted:
                self._recall_cache = (
                    current_session,
                    generation,
                    time.monotonic() + _RECALL_CACHE_SECONDS,
                    False,
                )
                self._recall_text = formatted
            else:
                self._recall_cache = None
                self._recall_text = ""

    def prefetch(self, query: str, session_id: str = "") -> str:
        """Consume the next-turn recall cache without doing remote work."""
        del query
        with self._state_lock:
            cache = self._recall_cache
            if (
                not self._active
                or cache is None
                or (session_id and session_id != self._session_id)
                or cache[0] != self._session_id
                or cache[1] != self._generation
                or cache[2] <= time.monotonic()
                or cache[3]
            ):
                if cache is not None and cache[2] <= time.monotonic():
                    self._recall_cache = None
                    self._recall_text = ""
                return ""
            self._recall_cache = (cache[0], cache[1], cache[2], True)
            return getattr(self, "_recall_text", "")

    @staticmethod
    def _format_recall(result: Any) -> str:
        results = result.get("results") if isinstance(result, Mapping) else None
        if not isinstance(results, list):
            return ""
        lines = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            text = next(
                (
                    item[key]
                    for key in ("text", "content", "summary")
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                "",
            )
            if not text:
                key, value = item.get("key"), item.get("value")
                if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip():
                    text = f"{key}: {value}"
                elif isinstance(value, str) and value.strip():
                    text = value
            normalized = _normalized_text(text, _MAX_RECALL_BYTES) if isinstance(text, str) else ""
            if normalized:
                lines.append(f"- {normalized}")
        if not lines:
            return ""
        return _truncate_utf8("## Eve Memory\n" + "\n".join(lines), _MAX_RECALL_BYTES)

    def sync_turn(
        self, user_content: Any, assistant_content: Any, *, session_id: str = "", messages: Any = None
    ) -> None:
        """Buffer a clean complete turn without reading Hermes history sidecars."""
        del messages
        if not isinstance(user_content, str) or not isinstance(assistant_content, str):
            return
        user = _normalized_text(user_content, _MAX_MESSAGE_BYTES)
        assistant = _normalized_text(assistant_content, _MAX_MESSAGE_BYTES)
        if not user or not assistant:
            return
        with self._state_lock:
            if (
                not self._active
                or not self._session_id
                or self._session_id in self._ended_session_ids
                or (session_id and session_id != self._session_id)
            ):
                return
            self._turn_buffer.append((user, assistant))
            while (
                len(self._turn_buffer) > _MAX_BUFFER_TURNS
                or _buffer_content_bytes(self._turn_buffer) > _MAX_BUFFER_BYTES
                or len(_transcript_from_turns(list(self._turn_buffer)).encode("utf-8"))
                > _MAX_SESSION_TRANSCRIPT_BYTES
            ):
                self._turn_buffer.popleft()

    def on_pre_compress(self, messages: Any) -> str:
        """Best-effort v1 checkpoint that never blocks Hermes compression."""
        normalized = self._normalize_messages(messages)
        with self._state_lock:
            if not self._active or not self._transport or not self._session_id or not normalized:
                return ""
            transport = self._transport
            session_id = self._session_id
            context = self._config["context"]
        try:
            transport.call_tool(
                "memory_pre_compact",
                {"session_id": session_id, "messages": normalized, "source_agent": "hermes_agent", "context": context},
            )
        except Exception:
            _LOGGER.warning("Eve Hermes pre-compaction failed")
        return ""

    @staticmethod
    def _normalize_messages(messages: Any) -> list[dict[str, str]]:
        if not isinstance(messages, list):
            return []
        normalized: list[dict[str, str]] = []
        total = 0
        for message in messages:
            if not isinstance(message, Mapping) or message.get("role") not in {"user", "assistant"}:
                continue
            content = _normalized_text(_content_text(message.get("content")), _MAX_BUFFER_BYTES - total)
            if not content:
                continue
            size = len(content.encode("utf-8"))
            if len(normalized) >= _MAX_BUFFER_MESSAGES or total + size > _MAX_BUFFER_BYTES:
                break
            normalized.append({"role": message["role"], "content": content})
            total += size
        return normalized

    def on_session_end(self, messages: Any = None) -> None:
        """Extract buffered turns, then record a bounded session end outcome."""
        del messages
        warning_required = False
        with self._state_lock:
            if not self._active or not self._transport or not self._session_id:
                return
            session_id = self._session_id
            if session_id in self._ended_session_ids:
                return
            worker = self._session_end_worker
            if worker is not None and not worker.is_alive():
                self._session_end_worker = None
                worker = None
            buffered = list(self._turn_buffer)
            self._turn_buffer.clear()
            self._ended_session_ids.append(session_id)
            if worker is not None:
                warning_required = True
            else:
                transport = self._transport
                context = self._config["context"]
                session_end_timeout_seconds = self._config["session_end_timeout_seconds"]
                details: dict[str, Any] = {"message_count": len(buffered) * 2}
                for key, value in (
                    ("platform", self._platform),
                    ("agent_identity", self._agent_identity),
                    ("agent_workspace", self._agent_workspace),
                    ("parent_session_id", self._parent_session_id),
                ):
                    if isinstance(value, str) and value:
                        details[key] = value
                transcript = _transcript_from_turns(buffered)
                worker = threading.Thread(
                    target=self._run_session_end,
                    args=(
                        transport,
                        session_id,
                        context,
                        session_end_timeout_seconds,
                        details,
                        transcript,
                    ),
                    daemon=True,
                )
                self._session_end_worker = worker
                worker.start()
        if warning_required:
            _LOGGER.warning("Eve Hermes session end did not finish before shutdown")
            return
        worker.join(_session_end_join_seconds(session_end_timeout_seconds))
        if worker.is_alive():
            _LOGGER.warning("Eve Hermes session end did not finish before shutdown")

    def _run_session_end(
        self,
        transport: EveMcpTransport,
        session_id: str,
        context: str,
        session_end_timeout_seconds: float,
        details: dict[str, Any],
        transcript: str,
    ) -> None:
        operation_timeout = httpx.Timeout(session_end_timeout_seconds)
        try:
            transport.call_tool(
                "memory_extract",
                {"transcript": transcript, "source": "hermes_agent", "source_agent": "hermes_agent", "session_id": session_id, "auto_store": True, "context": context, "min_importance": 5, "use_extraction": True},
                timeout_override=operation_timeout,
            )
        except Exception:
            _LOGGER.warning("Eve Hermes extraction failed")
        try:
            transport.call_tool(
                "memory_session_end",
                {"summary": f"Hermes session ended after {details['message_count']} messages.", "source_agent": "hermes_agent", "session_id": session_id, "context": context, "details": details, "status": "unknown"},
                timeout_override=operation_timeout,
            )
        except Exception:
            _LOGGER.warning("Eve Hermes session end failed")
        finally:
            with self._state_lock:
                if self._session_end_worker is threading.current_thread():
                    self._session_end_worker = None


def register(ctx: Any) -> None:
    ctx.register_memory_provider(EveMemoryProvider())
