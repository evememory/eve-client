"""Foundation contract tests for the Eve Hermes memory provider."""

from __future__ import annotations

import abc
import json
import logging
import stat
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import httpx
import pytest


class UnscopedSecretError(RuntimeError):
    """Fake Hermes fail-closed secret error."""


class MemoryProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @abc.abstractmethod
    def initialize(self, session_id: str, **kwargs: Any) -> None: ...

    @abc.abstractmethod
    def get_tool_schemas(self) -> list[dict[str, Any]]: ...


_secrets: dict[str, str] = {}


def get_secret(name: str, default: str = "") -> str:
    return _secrets.get(name, default)


agent_module = types.ModuleType("agent")
memory_provider_module = types.ModuleType("agent.memory_provider")
memory_provider_module.MemoryProvider = MemoryProvider
secret_scope_module = types.ModuleType("agent.secret_scope")
secret_scope_module.get_secret = get_secret
secret_scope_module.UnscopedSecretError = UnscopedSecretError
sys.modules.setdefault("agent", agent_module)
sys.modules.setdefault("agent.memory_provider", memory_provider_module)
sys.modules.setdefault("agent.secret_scope", secret_scope_module)

from eve_client.hermes_provider import provider as provider_module
from eve_client.hermes_provider.provider import EveMemoryProvider, register


class _RecordingTransport:
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.timeout_overrides: list[httpx.Timeout | None] = []

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_override: httpx.Timeout | None = None,
    ) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        self.timeout_overrides.append(timeout_override)
        return self.responses.pop(0) if self.responses else {}


def _active_provider(transport: _RecordingTransport) -> EveMemoryProvider:
    provider = EveMemoryProvider()
    provider._active = True
    provider._transport = transport  # type: ignore[assignment]
    provider._session_id = "session-1"
    return provider


def test_queue_prefetch_calls_eve_with_exact_bounded_recall_contract() -> None:
    # Break caught: recall omits provenance, scope, or configured search limits.
    transport = _RecordingTransport([{"results": [{"text": "remember this"}]}])
    provider = _active_provider(transport)
    provider._config.update(
        {"context": "naya", "recall_limit": 3, "min_similarity": 0.8, "request_timeout_seconds": 15}
    )

    provider.queue_prefetch("a useful query", "session-1")

    assert transport.calls == [
        (
            "memory_search",
            {
                "query": "a useful query",
                "source_agent": "hermes_agent",
                "context": "naya",
                "store": "all",
                "limit": 3,
                "min_similarity": 0.8,
            },
        )
    ]
    assert provider.prefetch("different next user message", "session-1") == "## Eve Memory\n- remember this"
    assert transport.timeout_overrides == [None]


def test_recall_formats_supported_shapes_and_consumes_one_cache_entry() -> None:
    # Break caught: recall reads unsupported fields or leaks its warmed result into more than one turn.
    transport = _RecordingTransport([{"results": [
        {"content": "  two\n words  "},
        {"summary": "three"},
        {"key": "topic", "value": "four"},
        {"value": "five"},
        {"ignored": "secret"},
    ]}])
    provider = _active_provider(transport)

    provider.queue_prefetch("q")

    assert provider.prefetch("unrelated") == "## Eve Memory\n- two words\n- three\n- topic: four\n- five"
    assert provider.prefetch("unrelated") == ""
    assert len(transport.calls) == 1


def test_failed_or_empty_recall_clears_prior_cache_and_disabled_or_mismatched_calls_do_nothing() -> None:
    # Break caught: stale recall survives a failed refresh or is fetched for a wrong/inactive scheduling context.
    transport = _RecordingTransport([{"results": [{"text": "old"}]}, {"results": []}])
    provider = _active_provider(transport)
    provider.queue_prefetch("first")
    provider.queue_prefetch("second")
    provider._config["auto_recall"] = False
    provider.queue_prefetch("disabled")
    provider._config["auto_recall"] = True
    provider.queue_prefetch("wrong session", "other")

    assert provider.prefetch("next") == ""
    assert [call[1]["query"] for call in transport.calls] == ["first", "second"]


def test_recall_limits_unicode_query_and_output_and_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: multibyte recall input/output exceeds its contract or stale recall remains consumable.
    clock = [0.0]
    monkeypatch.setattr("eve_client.hermes_provider.provider.time.monotonic", lambda: clock[0])
    transport = _RecordingTransport([{"results": [{"text": "é" * 5_000}]}])
    provider = _active_provider(transport)

    provider.queue_prefetch("é" * 2_001)

    assert len(transport.calls[0][1]["query"]) == 2_000
    assert len(provider._recall_text.encode("utf-8")) <= 8_192
    clock[0] = 301.0
    assert provider.prefetch("next") == ""


def test_failed_recall_clears_cache_with_redacted_diagnostic(caplog: pytest.LogCaptureFixture) -> None:
    # Break caught: failed search exposes exception data or leaves a prior result consumable.
    class FailingTransport(_RecordingTransport):
        def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((tool_name, arguments))
            raise RuntimeError("credential=secret")

    provider = _active_provider(_RecordingTransport([{"results": [{"text": "old"}]}]))
    provider.queue_prefetch("first")
    provider._transport = FailingTransport()  # type: ignore[assignment]
    with caplog.at_level(logging.WARNING):
        provider.queue_prefetch("second")

    assert provider.prefetch("next") == ""
    assert "Eve Hermes recall failed" in caplog.text
    assert "credential=secret" not in caplog.text


def test_switch_and_shutdown_prevent_late_search_from_committing() -> None:
    # Break caught: a completed old-session search can leak recall into a new or shut-down session.
    started = threading.Event()
    release = threading.Event()

    class BlockingTransport(_RecordingTransport):
        def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            started.set()
            assert release.wait(1)
            return {"results": [{"text": "late"}]}

    provider = _active_provider(BlockingTransport())
    worker = threading.Thread(target=provider.queue_prefetch, args=("query",))
    worker.start()
    assert started.wait(1)
    provider.on_session_switch("session-2", "session-1")
    provider.shutdown()
    release.set()
    worker.join(1)

    assert provider.prefetch("next") == ""


def test_same_session_switch_invalidates_buffer_cache_and_late_search() -> None:
    # Break caught: a same-ID lifecycle hook retains old turn state or accepts its in-flight recall.
    started = threading.Event()
    release = threading.Event()

    class BlockingTransport(_RecordingTransport):
        def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            started.set()
            assert release.wait(1)
            return {"results": [{"text": "late"}]}

    provider = _active_provider(BlockingTransport())
    provider.sync_turn("old user", "old assistant")
    generation = provider._generation
    worker = threading.Thread(target=provider.queue_prefetch, args=("query",))
    worker.start()
    assert started.wait(1)
    provider.on_session_switch("session-1", "new-parent")
    release.set()
    worker.join(1)

    assert provider._generation == generation + 1
    assert provider._parent_session_id == "new-parent"
    assert list(provider._turn_buffer) == []
    assert provider.prefetch("next") == ""


def test_distinct_session_switch_isolates_cached_recall_and_turns() -> None:
    # Break caught: a reset/branch/resume hook carries old-session recall or transcript input forward.
    transport = _RecordingTransport([{"results": [{"text": "old recall"}]}])
    provider = _active_provider(transport)
    provider.queue_prefetch("query")
    provider.sync_turn("old user", "old assistant")

    provider.on_session_switch("session-2", "session-1")

    assert provider._session_id == "session-2"
    assert provider._parent_session_id == "session-1"
    assert list(provider._turn_buffer) == []
    assert provider.prefetch("next", "session-2") == ""


def test_initialize_rejects_missing_or_nonstring_session_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Break caught: an active provider can make remote calls without a concrete current session.
    provider = _provider_with_secret(monkeypatch)
    for invalid_session_id in ("", 123):
        with pytest.raises(ValueError, match="session ID"):
            provider.initialize(invalid_session_id, hermes_home=str(tmp_path))  # type: ignore[arg-type]
        assert provider._active is False
        assert provider._transport is None


def test_session_end_evicts_complete_turns_before_transcript_limit() -> None:
    # Break caught: transcript labels reduce the frozen content budget or extraction splits a message line.
    transport = _RecordingTransport([{}, {}])
    provider = _active_provider(transport)
    for _ in range(4):
        provider.sync_turn("u" * 4096, "a" * 4096)

    provider.on_session_end()

    extract = transport.calls[0][1]
    assert extract["transcript"].endswith("Assistant: " + "a" * 4096)
    assert len(extract["transcript"].encode("utf-8")) <= 33147
    assert transport.calls[1][1]["details"]["message_count"] == 8


def test_sync_turn_is_network_free_complete_turn_bounded_and_ignores_sidecars() -> None:
    # Break caught: provider buffers partial/tool payload history or performs network I/O on a turn path.
    transport = _RecordingTransport()
    provider = _active_provider(transport)
    for index in range(21):
        provider.sync_turn(
            f"user {index}", f"assistant {index}",
            messages=[{"role": "tool", "api_content": "sensitive"}],
        )
    provider.sync_turn("user", "", messages=[{"api_content": "also sensitive"}])

    assert transport.calls == []
    assert len(provider._turn_buffer) == 20
    assert provider._turn_buffer[0] == ("user 1", "assistant 1")
    assert all("sensitive" not in value for turn in provider._turn_buffer for value in turn)


def test_sync_turn_limits_unicode_messages_and_evicts_complete_old_turns() -> None:
    # Break caught: turn limits split UTF-8 content or retain a partial old turn under byte pressure.
    provider = _active_provider(_RecordingTransport())
    for index in range(10):
        provider.sync_turn(f"{index}" + "é" * 4_096, "é" * 4_096)

    assert all(len(value.encode("utf-8")) <= 4_096 for turn in provider._turn_buffer for value in turn)
    assert len(provider._turn_buffer) < 10
    assert all(len(turn) == 2 for turn in provider._turn_buffer)


def test_pre_compress_filters_history_and_returns_empty_after_one_best_effort_call() -> None:
    # Break caught: compaction forwards tool/sidecar data or treats the checkpoint reply as Hermes content.
    transport = _RecordingTransport([{"status": "stored"}])
    provider = _active_provider(transport)
    provider._config["request_timeout_seconds"] = 15

    returned = provider.on_pre_compress([
        {"role": "system", "content": "ignore"},
        {"role": "user", "content": [{"type": "text", "text": " first "}, {"type": "tool_result", "text": "secret"}], "api_content": "sidecar"},
        {"role": "assistant", "content": [{"type": "output_text", "text": "second"}]},
    ])

    assert returned == ""
    assert transport.calls == [(
        "memory_pre_compact",
        {"session_id": "session-1", "messages": [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ], "source_agent": "hermes_agent", "context": "personal"},
    )]
    assert transport.timeout_overrides == [None]


def test_pre_compress_applies_count_byte_bounds_and_fails_open(caplog: pytest.LogCaptureFixture) -> None:
    # Break caught: compression sends unbounded history or leaks its transport failure into Hermes.
    transport = _RecordingTransport([{}])
    provider = _active_provider(transport)
    messages = [{"role": "user", "content": "x" * 1_000} for _ in range(50)]
    assert provider.on_pre_compress(messages) == ""
    sent = transport.calls[0][1]["messages"]
    assert len(sent) <= 40
    assert sum(len(message["content"].encode("utf-8")) for message in sent) <= 32_768

    class FailingTransport(_RecordingTransport):
        def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("private details")

    provider._transport = FailingTransport()  # type: ignore[assignment]
    with caplog.at_level(logging.WARNING):
        assert provider.on_pre_compress(messages[:1]) == ""
    assert "Eve Hermes pre-compaction failed" in caplog.text
    assert "private details" not in caplog.text


def test_session_end_extracts_buffer_then_records_redacted_metadata_once() -> None:
    # Break caught: session end uses raw passed history, reverses operations, or sends transcript content in event details.
    transport = _RecordingTransport([{"items": []}, {"status": "ok"}])
    provider = _active_provider(transport)
    provider._platform = "cli"
    provider._parent_session_id = "parent-1"
    provider.sync_turn("question", "answer")

    provider.on_session_end([{"role": "tool", "content": "do not use"}])
    provider.on_session_end([])

    assert transport.calls == [
        ("memory_extract", {
            "transcript": "User: question\nAssistant: answer", "source": "hermes_agent",
            "source_agent": "hermes_agent", "session_id": "session-1", "auto_store": True,
            "context": "personal", "min_importance": 5, "use_extraction": True,
        }),
        ("memory_session_end", {
            "summary": "Hermes session ended after 2 messages.", "source_agent": "hermes_agent",
            "session_id": "session-1", "context": "personal",
            "details": {"message_count": 2, "platform": "cli", "parent_session_id": "parent-1"},
            "status": "unknown",
        }),
    ]
    assert list(provider._turn_buffer) == []


def test_session_end_uses_its_configured_timeout_for_both_calls() -> None:
    # Break caught: session end ignores its dedicated operation timeout.
    transport = _RecordingTransport([{}, {}])
    provider = _active_provider(transport)
    provider._config["session_end_timeout_seconds"] = 17

    provider.on_session_end()

    assert transport.timeout_overrides == [httpx.Timeout(17), httpx.Timeout(17)]


@pytest.mark.parametrize(
    ("timeout_seconds", "expected"),
    [(5, 11), (20, 41), (30, 61)],
)
def test_session_end_join_allowance_is_two_operation_budgets_plus_one_second(
    timeout_seconds: float, expected: float
) -> None:
    # Break caught: Hermes shutdown has a separate fixed join setting.
    assert provider_module._session_end_join_seconds(timeout_seconds) == expected


def test_session_end_returns_after_bounded_join_and_abandons_a_new_session_while_worker_is_alive(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Break caught: a blocked end hook delays Hermes shutdown or starts another remote end worker.
    started = threading.Event()
    release = threading.Event()

    class BlockingTransport(_RecordingTransport):
        def call_tool(
            self,
            tool_name: str,
            arguments: dict[str, Any],
            timeout_override: httpx.Timeout | None = None,
        ) -> dict[str, Any]:
            self.calls.append((tool_name, arguments))
            self.timeout_overrides.append(timeout_override)
            started.set()
            assert release.wait(1)
            return {}

    monkeypatch.setattr(provider_module, "_session_end_join_seconds", lambda _: 0.01)
    transport = BlockingTransport()
    provider = _active_provider(transport)
    provider.sync_turn("old user", "old assistant")

    with caplog.at_level(logging.WARNING):
        began = time.monotonic()
        provider.on_session_end()
        elapsed = time.monotonic() - began

        assert started.is_set()
        old_worker = provider._session_end_worker
        assert old_worker is not None and old_worker.is_alive()
        assert elapsed < 0.25

        provider.on_session_switch("session-2")
        new_transport = _RecordingTransport()
        with provider._state_lock:
            provider._transport = new_transport  # type: ignore[assignment]
        provider.sync_turn("new user", "new assistant")
        provider.on_session_end()

    assert provider._session_id in provider._ended_session_ids
    assert list(provider._turn_buffer) == []
    assert provider._session_end_worker is old_worker
    assert "Eve Hermes session end did not finish before shutdown" in caplog.text
    assert "old user" not in caplog.text
    assert "old assistant" not in caplog.text

    provider.shutdown()
    release.set()
    old_worker.join(1)

    assert transport.calls == [
        ("memory_extract", {
            "transcript": "User: old user\nAssistant: old assistant", "source": "hermes_agent",
            "source_agent": "hermes_agent", "session_id": "session-1", "auto_store": True,
            "context": "personal", "min_importance": 5, "use_extraction": True,
        }),
        ("memory_session_end", {
            "summary": "Hermes session ended after 2 messages.", "source_agent": "hermes_agent",
            "session_id": "session-1", "context": "personal", "details": {"message_count": 2},
            "status": "unknown",
        }),
    ]
    assert new_transport.calls == []


def test_shutdown_does_not_join_a_blocked_session_end_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: shutdown waits for a remote end request after Hermes has begun its drain.
    started = threading.Event()
    release = threading.Event()

    class BlockingTransport(_RecordingTransport):
        def call_tool(
            self,
            tool_name: str,
            arguments: dict[str, Any],
            timeout_override: httpx.Timeout | None = None,
        ) -> dict[str, Any]:
            started.set()
            assert release.wait(1)
            return {}

    monkeypatch.setattr(provider_module, "_session_end_join_seconds", lambda _: 0.01)
    provider = _active_provider(BlockingTransport())

    provider.on_session_end()
    assert started.is_set()
    worker = provider._session_end_worker
    assert worker is not None
    began = time.monotonic()
    provider.shutdown()
    assert time.monotonic() - began < 0.1

    release.set()
    worker.join(1)


def test_completed_session_end_worker_allows_a_distinct_session_to_end() -> None:
    # Break caught: a completed worker reference blocks the next distinct session from recording its end.
    transport = _RecordingTransport([{}, {}, {}, {}])
    provider = _active_provider(transport)

    provider.on_session_end()
    provider.on_session_switch("session-2")
    provider.on_session_end()

    assert [name for name, _ in transport.calls] == [
        "memory_extract", "memory_session_end", "memory_extract", "memory_session_end"
    ]


def test_session_end_zero_messages_and_both_failures_remain_ordered_and_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Break caught: zero-message end skips extraction, or a failure prevents/refines the required event call.
    class FailingTransport(_RecordingTransport):
        def call_tool(
            self,
            tool_name: str,
            arguments: dict[str, Any],
            timeout_override: httpx.Timeout | None = None,
        ) -> dict[str, Any]:
            self.calls.append((tool_name, arguments))
            self.timeout_overrides.append(timeout_override)
            raise RuntimeError(f"secret from {tool_name}")

    transport = FailingTransport()
    provider = _active_provider(transport)
    with caplog.at_level(logging.WARNING):
        provider.on_session_end()
        provider.on_session_end()

    assert [name for name, _ in transport.calls] == ["memory_extract", "memory_session_end"]
    assert transport.calls[0][1]["transcript"] == ""
    assert transport.calls[1][1]["details"] == {"message_count": 0}
    assert transport.timeout_overrides == [httpx.Timeout(20), httpx.Timeout(20)]
    assert "Eve Hermes extraction failed" in caplog.text
    assert "Eve Hermes session end failed" in caplog.text
    assert "secret from" not in caplog.text


def test_resumed_ended_session_does_not_extract_or_end_twice() -> None:
    # Break caught: a resumed session ID can learn a second transcript after its original end hook.
    transport = _RecordingTransport([{}, {}])
    provider = _active_provider(transport)
    provider.sync_turn("first user", "first assistant")
    provider.on_session_end()

    provider.on_session_switch("session-1", "parent-1")
    provider.sync_turn("resumed user", "resumed assistant")
    provider.on_session_end()

    assert [name for name, _ in transport.calls] == ["memory_extract", "memory_session_end"]
    assert list(provider._turn_buffer) == []


def test_inactive_hooks_make_no_lifecycle_calls() -> None:
    # Break caught: inactive/non-primary provider state can call Eve lifecycle operations.
    provider = EveMemoryProvider()
    provider.queue_prefetch("query")
    provider.sync_turn("user", "assistant")
    assert provider.on_pre_compress([{"role": "user", "content": "message"}]) == ""
    provider.on_session_end()
    provider.on_session_switch("session-2", "parent")
    assert provider.prefetch("next") == ""


def _provider_with_secret(monkeypatch: pytest.MonkeyPatch, value: str = "scoped-key") -> EveMemoryProvider:
    monkeypatch.setattr(
        "eve_client.hermes_provider.provider.get_secret", lambda name, default="": value
    )
    return EveMemoryProvider()


def test_provider_satisfies_hermes_abc_and_registers_exactly_once() -> None:
    # Break caught: provider cannot load as a Hermes memory provider or registers the wrong object.
    provider = EveMemoryProvider()
    registered: list[MemoryProvider] = []

    class Context:
        def register_memory_provider(self, value: MemoryProvider) -> None:
            registered.append(value)

    assert isinstance(provider, MemoryProvider)
    assert provider.name == "eve"
    assert provider.pre_compress_checkpoint_api_version == 1
    assert register(Context()) is None
    assert len(registered) == 1
    assert isinstance(registered[0], EveMemoryProvider)


def test_provider_has_no_model_tools() -> None:
    # Break caught: this foundational slice exposes model-callable Eve tools.
    assert EveMemoryProvider().get_tool_schemas() == []


def test_availability_uses_scoped_key_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: availability reads ambient env or attempts a network probe.
    calls: list[tuple[str, str]] = []

    def scoped_secret(name: str, default: str = "") -> str:
        calls.append((name, default))
        return "scoped-key"

    monkeypatch.setattr("eve_client.hermes_provider.provider.get_secret", scoped_secret)
    assert EveMemoryProvider().is_available() is True
    for invalid_key in ("", "   ", 123):
        monkeypatch.setattr(
            "eve_client.hermes_provider.provider.get_secret", lambda *args, value=invalid_key: value
        )
        assert EveMemoryProvider().is_available() is False
    assert calls == [("EVE_API_KEY", "")]


def test_availability_propagates_unscoped_secret_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Break caught: multiplex isolation failures are hidden by availability checks.
    def fail(*args: Any, **kwargs: Any) -> str:
        raise UnscopedSecretError("no scope")

    monkeypatch.setattr("eve_client.hermes_provider.provider.get_secret", fail)
    with pytest.raises(UnscopedSecretError):
        EveMemoryProvider().is_available()


def test_returns_exact_config_schema() -> None:
    # Break caught: configuration exposes an unsupported or missing control.
    assert EveMemoryProvider().get_config_schema() == [
        {"key": "api_key", "description": "Eve API key", "secret": True, "required": True, "env_var": "EVE_API_KEY", "url": "https://evemem.com/app"},
        {"key": "context", "description": "Eve memory context", "type": "text", "default": "personal"},
        {"key": "auto_recall", "description": "Enable automatic Eve recall", "type": "boolean", "default": True},
        {"key": "recall_limit", "description": "Maximum recalled memories", "type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        {"key": "min_similarity", "description": "Minimum recall similarity", "type": "number", "default": 0.7, "minimum": 0, "maximum": 1},
        {"key": "request_timeout_seconds", "description": "Eve request timeout in seconds", "type": "number", "default": 5, "minimum": 1, "maximum": 15},
        {"key": "session_end_timeout_seconds", "description": "Eve session-end timeout in seconds", "type": "number", "default": 20, "minimum": 5, "maximum": 30},
    ]


def test_save_config_is_profile_local_atomic_private_and_preserves_recognized_values(tmp_path: Path) -> None:
    # Break caught: setup stores credentials/unknown data or replaces existing recognized settings.
    path = tmp_path / "eve.json"
    path.write_text(json.dumps({"context": "naya", "recall_limit": 9, "unknown": "drop"}))
    provider = EveMemoryProvider()

    provider.save_config(
        {"auto_recall": False, "api_key": "never-persist", "EVE_API_KEY": "never-persist", "unknown": "drop"},
        str(tmp_path),
    )

    assert json.loads(path.read_text()) == {
        "context": "naya", "recall_limit": 9, "auto_recall": False
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "values",
    [
        {"context": value}
        for value in (1, "", "  ")
    ]
    + [
        {"auto_recall": "yes"},
        {"recall_limit": 0},
        {"recall_limit": True},
        {"min_similarity": 1.1},
        {"request_timeout_seconds": 16},
        {"session_end_timeout_seconds": 4},
        {"session_end_timeout_seconds": 31},
    ],
)
def test_save_config_rejects_invalid_values_before_replacing_file(tmp_path: Path, values: dict[str, Any]) -> None:
    # Break caught: invalid configuration silently changes or corrupts the profile file.
    path = tmp_path / "eve.json"
    path.write_text('{"context":"personal"}')
    with pytest.raises(ValueError):
        EveMemoryProvider().save_config(values, str(tmp_path))
    assert path.read_text() == '{"context":"personal"}'


@pytest.mark.parametrize(
    "raw", ["not-json", "[]", '{"recall_limit": 99}', '{"context":""}', '{"context":"  "}']
)
def test_primary_initialize_fails_closed_for_invalid_profile_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str
) -> None:
    # Break caught: malformed or invalid profile configuration is silently accepted.
    (tmp_path / "eve.json").write_text(raw)
    provider = _provider_with_secret(monkeypatch)
    with pytest.raises(ValueError):
        provider.initialize("session-1", hermes_home=str(tmp_path))
    assert provider._transport is None


def test_save_config_normalizes_official_terminal_setup_values(tmp_path: Path) -> None:
    # Break caught: Hermes setup strings are rejected despite matching the declared schema.
    EveMemoryProvider().save_config(
        {
            "context": "personal",
            "auto_recall": "True",
            "recall_limit": "5",
            "min_similarity": "0.7",
            "request_timeout_seconds": "5",
            "session_end_timeout_seconds": "20.0",
        },
        str(tmp_path),
    )
    assert json.loads((tmp_path / "eve.json").read_text()) == {
        "context": "personal",
        "auto_recall": True,
        "recall_limit": 5,
        "min_similarity": 0.7,
        "request_timeout_seconds": 5.0,
        "session_end_timeout_seconds": 20.0,
    }


@pytest.mark.parametrize(
    "values",
    [
        {"auto_recall": "yes"},
        {"auto_recall": " true"},
        {"recall_limit": "5.0"},
        {"recall_limit": "05"},
        {"min_similarity": "NaN"},
        {"request_timeout_seconds": "Infinity"},
        {"session_end_timeout_seconds": " 20"},
    ],
)
def test_save_config_rejects_ambiguous_or_noncanonical_setup_strings(
    tmp_path: Path, values: dict[str, Any]
) -> None:
    # Break caught: setup accepts values outside the strict declared field formats.
    with pytest.raises(ValueError):
        EveMemoryProvider().save_config(values, str(tmp_path))


def test_primary_initialize_uses_defaults_metadata_and_bounded_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Break caught: primary startup omits defaults, metadata, or a bounded transport.
    created: list[dict[str, Any]] = []

    class Transport:
        def __init__(self, endpoint: str, api_key: str, timeout: httpx.Timeout) -> None:
            created.append({"endpoint": endpoint, "api_key": api_key, "timeout": timeout})

    monkeypatch.setattr("eve_client.hermes_provider.provider.EveMcpTransport", Transport)
    provider = _provider_with_secret(monkeypatch)
    provider.initialize(
        "session-1",
        hermes_home=str(tmp_path),
        platform="cli",
        agent_identity="alice",
        agent_workspace="workspace",
        parent_session_id="parent-1",
    )

    assert len(created) == 1
    assert created[0]["endpoint"] == "https://mcp.evemem.com/mcp"
    assert created[0]["api_key"] == "scoped-key"
    timeout = created[0]["timeout"]
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (5, 5, 5, 5)
    assert provider._session_id == "session-1"
    assert provider._platform == "cli"
    assert provider._agent_identity == "alice"
    assert provider._agent_workspace == "workspace"
    assert provider._parent_session_id == "parent-1"


@pytest.mark.parametrize("invalid_key", ["", "  ", 123])
def test_primary_initialize_rejects_invalid_scoped_key_and_invalidates_prior_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, invalid_key: Any
) -> None:
    # Break caught: a failed primary reinitialization leaves an old profile active.
    provider = _provider_with_secret(monkeypatch)
    monkeypatch.setattr("eve_client.hermes_provider.provider.EveMcpTransport", lambda *args: object())
    provider.initialize("session-1", hermes_home=str(tmp_path))
    monkeypatch.setattr("eve_client.hermes_provider.provider.get_secret", lambda *args: invalid_key)

    with pytest.raises(ValueError, match="Eve API key is required"):
        provider.initialize("session-2", hermes_home=str(tmp_path))

    assert provider._active is False
    assert provider._transport is None
    assert provider._session_id == ""


@pytest.mark.parametrize("agent_context", ["subagent", "cron", "flush"])
def test_non_primary_initialize_stays_inactive_without_transport_or_lifecycle_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, agent_context: str
) -> None:
    # Break caught: subagents activate Eve state or call the hosted lifecycle path.
    def no_transport(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("transport must not be created")

    monkeypatch.setattr("eve_client.hermes_provider.provider.EveMcpTransport", no_transport)
    provider = _provider_with_secret(monkeypatch)
    provider.initialize("session-1", hermes_home=str(tmp_path), agent_context=agent_context)
    assert provider._active is False
    assert provider._transport is None


def test_non_primary_initialize_clears_existing_primary_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Break caught: a subagent inherits an active primary Eve transport or session.
    provider = _provider_with_secret(monkeypatch)
    monkeypatch.setattr("eve_client.hermes_provider.provider.EveMcpTransport", lambda *args: object())
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")

    provider.initialize("session-2", hermes_home=str(tmp_path), agent_context="subagent")

    assert provider._active is False
    assert provider._transport is None
    assert provider._session_id == ""
    assert provider._platform == ""


def test_shutdown_immediately_invalidates_state_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Break caught: shutdown waits on or preserves a live transport/session.
    provider = _provider_with_secret(monkeypatch)
    monkeypatch.setattr("eve_client.hermes_provider.provider.EveMcpTransport", lambda *args: object())
    provider.initialize("session-1", hermes_home=str(tmp_path))
    provider.shutdown()
    assert provider._active is False
    assert provider._transport is None
    assert provider._session_id == ""
