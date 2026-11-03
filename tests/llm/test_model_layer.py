import asyncio
from pathlib import Path

import pytest

from boardgames.llm.cache import CachedChatModel, DirectoryResponseStore, cache_key
from boardgames.llm.model import (
    ChatModel,
    Completion,
    ForcedTool,
    Message,
    ModelRequestError,
    ModelSettings,
    ModelUnavailableError,
    ToolCall,
    ToolSpec,
    TransientModelError,
    messages_json,
)
from boardgames.llm.retry import RetryingChatModel
from tests.llm.fakes import QueuedChatModel, reply, tool_calls_reply

SETTINGS = ModelSettings(model="anthropic/claude-haiku-5-5")
MESSAGES = (Message("system", "rules"), Message("user", "your move"))
TOOL = ToolSpec("submit_action", "Submit your action.", {"type": "object"})
LOOKUP = ToolSpec("get_state", "Read the state.", {"type": "object"})


class RecordedSleep:
    """Sleep stand-in that records requested delays instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        return

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        return


def complete(model: ChatModel, settings: ModelSettings = SETTINGS) -> Completion:
    return asyncio.run(
        model.complete(MESSAGES, settings, (TOOL,), ForcedTool(TOOL.name))
    )


def test_messages_json_carries_tool_fields_only_when_set() -> None:
    call = ToolCall("call_1", "get_state", "{}")
    messages = (
        Message("assistant", "", tool_calls=(call,)),
        Message("tool", "board", tool_call_id="call_1"),
    )
    assert messages_json(MESSAGES) == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "your move"},
    ]
    assert messages_json(messages) == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_state", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": "board", "tool_call_id": "call_1"},
    ]
    return


def test_retry_counts_transient_failures_and_backs_off() -> None:
    inner = QueuedChatModel(
        [TransientModelError("429"), TransientModelError("timeout"), reply("ok")]
    )
    sleep = RecordedSleep()
    model = RetryingChatModel(inner, sleep=sleep)
    completion = complete(model)
    assert (completion.text, completion.api_retries) == ("ok", 2)
    assert sleep.delays == [1.0, 2.0]
    return


def test_retry_gives_up_after_max_attempts() -> None:
    inner = QueuedChatModel([TransientModelError("503")] * 3)
    model = RetryingChatModel(inner, max_attempts=3, sleep=RecordedSleep())
    with pytest.raises(ModelUnavailableError, match="failed 3 times; last: 503"):
        complete(model)
    return


def test_retry_does_not_retry_rejected_requests() -> None:
    inner = QueuedChatModel([ModelRequestError("bad key"), reply("unused")])
    with pytest.raises(ModelRequestError):
        complete(RetryingChatModel(inner, sleep=RecordedSleep()))
    assert len(inner.calls) == 1
    return


def test_cache_returns_stored_reply_without_calling_the_model(tmp_path: Path) -> None:
    inner = QueuedChatModel([reply("first", '{"action": "a1"}', reasoning="why")])
    model = CachedChatModel(inner, DirectoryResponseStore(tmp_path))
    first = complete(model)
    second = complete(model)
    assert len(inner.calls) == 1
    assert (second.text, second.tool_arguments) == ("first", '{"action": "a1"}')
    assert second.reasoning == "why"
    assert (second.cost_usd, second.is_cached) == (0.0, True)
    assert first.is_cached is False
    return


def test_cache_misses_when_the_seed_changes(tmp_path: Path) -> None:
    inner = QueuedChatModel([reply("a"), reply("b")])
    model = CachedChatModel(inner, DirectoryResponseStore(tmp_path))
    complete(model, ModelSettings(model="m", seed=1))
    assert complete(model, ModelSettings(model="m", seed=2)).text == "b"
    return


def test_cache_key_changes_with_the_tools_and_the_choice() -> None:
    forced = cache_key(MESSAGES, SETTINGS, (TOOL,), ForcedTool(TOOL.name))
    assert cache_key(MESSAGES, SETTINGS, (TOOL, LOOKUP), "auto") != forced
    assert cache_key(MESSAGES, SETTINGS, (TOOL,), "auto") != forced
    assert cache_key(MESSAGES, SETTINGS, (), "auto") == cache_key(
        MESSAGES, SETTINGS, (), "required"
    )
    return


def test_cache_round_trips_several_tool_calls(tmp_path: Path) -> None:
    calls = (ToolCall("c1", "get_state", "{}"), ToolCall("c2", "check_action", "{}"))
    inner = QueuedChatModel([tool_calls_reply(calls)])
    model = CachedChatModel(inner, DirectoryResponseStore(tmp_path))
    complete(model)
    assert complete(model).tool_calls == calls
    return
