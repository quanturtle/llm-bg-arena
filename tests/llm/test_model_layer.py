import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from tabletop_arena.llm.cache import CachedChatModel, DirectoryResponseStore
from tabletop_arena.llm.litellm_model import (
    completion_from,
    request_arguments,
    table_prices,
)
from tabletop_arena.llm.model import (
    ChatModel,
    Completion,
    Message,
    ModelRequestError,
    ModelSettings,
    ModelUnavailableError,
    TokenPrices,
    ToolSpec,
    TransientModelError,
    Usage,
    cost_usd,
)
from tabletop_arena.llm.retry import RetryingChatModel
from tests.llm.fakes import QueuedChatModel, reply

SETTINGS = ModelSettings(model="anthropic/claude-haiku-5-5")
MESSAGES = (Message("system", "rules"), Message("user", "your move"))
TOOL = ToolSpec("submit_action", "Submit your action.", {"type": "object"})


class RecordedSleep:
    """Sleep stand-in that records requested delays instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        return

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        return


def complete(model: ChatModel, settings: ModelSettings = SETTINGS) -> Completion:
    return asyncio.run(model.complete(MESSAGES, settings, TOOL))


def test_cost_uses_per_million_prices() -> None:
    usage = Usage(prompt_tokens=2_000, completion_tokens=500)
    assert cost_usd(usage, TokenPrices(1.0, 5.0)) == pytest.approx(0.0045)
    assert cost_usd(usage, None) is None
    return


def test_table_prices_strip_provider_prefixes() -> None:
    table = {
        "claude-haiku-5-5": {
            "input_cost_per_token": 1e-6,
            "output_cost_per_token": 5e-6,
        }
    }
    assert table_prices("openrouter/anthropic/claude-haiku-5-5", table) == TokenPrices(
        1.0, 5.0
    )
    assert table_prices("unknown/model", table) is None
    return


def test_request_arguments_force_the_tool_and_skip_unset_options() -> None:
    arguments = request_arguments(MESSAGES, SETTINGS, TOOL)
    assert arguments["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_action"},
    }
    assert arguments["messages"][1] == {"role": "user", "content": "your move"}
    assert "temperature" not in arguments
    assert "reasoning_effort" not in arguments
    assert arguments["drop_params"] is True
    return


def test_request_arguments_pass_set_options() -> None:
    settings = ModelSettings(
        model="openai/gpt-x", temperature=0.2, reasoning_effort="low", seed=4
    )
    arguments = request_arguments(MESSAGES, settings, None)
    assert (arguments["temperature"], arguments["reasoning_effort"]) == (0.2, "low")
    assert arguments["seed"] == 4
    assert "tools" not in arguments
    return


def test_completion_from_reads_tool_arguments_and_usage() -> None:
    call = SimpleNamespace(function=SimpleNamespace(arguments='{"action": "b2"}'))
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))
        ],
        usage=SimpleNamespace(prompt_tokens=1_000, completion_tokens=100),
    )
    completion = completion_from(response, TokenPrices(1.0, 5.0))
    assert completion.text == ""
    assert completion.tool_arguments == '{"action": "b2"}'
    assert completion.cost_usd == pytest.approx(0.0015)
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
    inner = QueuedChatModel([reply("first", '{"action": "a1"}')])
    model = CachedChatModel(inner, DirectoryResponseStore(tmp_path))
    first = complete(model)
    second = complete(model)
    assert len(inner.calls) == 1
    assert (second.text, second.tool_arguments) == ("first", '{"action": "a1"}')
    assert (second.cost_usd, second.is_cached) == (0.0, True)
    assert first.is_cached is False
    return


def test_cache_misses_when_the_seed_changes(tmp_path: Path) -> None:
    inner = QueuedChatModel([reply("a"), reply("b")])
    model = CachedChatModel(inner, DirectoryResponseStore(tmp_path))
    complete(model, ModelSettings(model="m", seed=1))
    assert complete(model, ModelSettings(model="m", seed=2)).text == "b"
    return
