import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from boardgames.llm.model import (
    Completion,
    ForcedTool,
    Message,
    ModelRequestError,
    ModelSettings,
    ToolCall,
    ToolSpec,
    TransientModelError,
)
from boardgames.llm.openrouter_model import (
    OpenRouterChatModel,
    ResponsePayload,
    completion_from,
    failure,
    request_body,
)

SETTINGS = ModelSettings(model="anthropic/claude-haiku-5-5")
MESSAGES = (Message("system", "rules"), Message("user", "your move"))
TOOL = ToolSpec("submit_action", "Submit your action.", {"type": "object"})

type Handler = Callable[[httpx.Request], httpx.Response]


def reply_payload(
    content: str | None = "b2", tool_arguments: str | None = None
) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": content}
    if tool_arguments is not None:
        message["tool_calls"] = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "submit_action", "arguments": tool_arguments},
            }
        ]
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 1_000, "completion_tokens": 100, "cost": 0.0015},
    }


def model_with(handler: Handler) -> OpenRouterChatModel:
    return OpenRouterChatModel("test-key", transport=httpx.MockTransport(handler))


def complete(model: OpenRouterChatModel) -> Completion:
    return asyncio.run(
        model.complete(MESSAGES, SETTINGS, (TOOL,), ForcedTool("submit_action"))
    )


def test_request_body_forces_the_tool_and_skips_unset_options() -> None:
    body = request_body(MESSAGES, SETTINGS, (TOOL,), ForcedTool("submit_action"))
    assert body["model"] == "anthropic/claude-haiku-5-5"
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_action"},
    }
    assert body["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "your move"},
    ]
    assert body["usage"] == {"include": True}
    assert "temperature" not in body
    assert "reasoning" not in body
    return


def test_request_body_passes_set_options() -> None:
    settings = ModelSettings(
        model="openai/gpt-x", temperature=0.2, reasoning_effort="low", seed=4
    )
    body = request_body(MESSAGES, settings, (), "auto")
    assert (body["temperature"], body["seed"]) == (0.2, 4)
    assert body["reasoning"] == {"effort": "low"}
    assert "tools" not in body
    assert "tool_choice" not in body
    return


def test_request_body_sends_auto_and_required_choices_as_strings() -> None:
    assert request_body(MESSAGES, SETTINGS, (TOOL,), "auto")["tool_choice"] == "auto"
    required = request_body(MESSAGES, SETTINGS, (TOOL,), "required")
    assert required["tool_choice"] == "required"
    return


def test_completion_from_reads_every_tool_call() -> None:
    payload = reply_payload(content=None)
    payload["choices"][0]["message"]["tool_calls"] = [  # type: ignore[index]
        {"id": "c1", "function": {"name": "get_state", "arguments": "{}"}},
        {"id": "c2", "function": {"name": "check_action", "arguments": '{"a": 1}'}},
    ]
    completion = completion_from(ResponsePayload.model_validate(payload), "m")
    assert completion.tool_calls == (
        ToolCall("c1", "get_state", "{}"),
        ToolCall("c2", "check_action", '{"a": 1}'),
    )
    return


def test_completion_from_reads_tool_arguments_usage_cost_and_reasoning() -> None:
    payload = reply_payload(content=None, tool_arguments='{"action": "b2"}')
    payload["choices"][0]["message"]["reasoning"] = "center is best"  # type: ignore[index]
    completion = completion_from(ResponsePayload.model_validate(payload), "m")
    assert completion.text == ""
    assert completion.tool_arguments == '{"action": "b2"}'
    assert (completion.usage.prompt_tokens, completion.usage.completion_tokens) == (
        1_000,
        100,
    )
    assert completion.cost_usd == pytest.approx(0.0015)
    assert completion.reasoning == "center is best"
    return


def test_completion_without_choices_is_rejected() -> None:
    with pytest.raises(ModelRequestError, match="no choices"):
        completion_from(ResponsePayload(), "m")
    return


def test_failure_classifies_statuses_and_error_bodies() -> None:
    assert failure(200, ResponsePayload()) is None
    assert failure(429, ResponsePayload()) == ("transient", "HTTP 429")
    assert failure(503, ResponsePayload()) == ("transient", "HTTP 503")
    assert failure(401, ResponsePayload()) == ("rejected", "HTTP 401")
    in_body = ResponsePayload.model_validate(
        {"error": {"code": 502, "message": "provider down"}}
    )
    assert failure(200, in_body) == ("transient", "provider down")
    return


def test_complete_sends_the_key_and_reads_the_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=reply_payload(tool_arguments='{"a": 1}'))

    completion = complete(model_with(handler))
    assert seen[0].url == "https://openrouter.ai/api/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert json.loads(seen[0].content)["model"] == "anthropic/claude-haiku-5-5"
    assert completion.tool_arguments == '{"a": 1}'
    return


def test_rate_limit_is_transient_and_bad_key_is_rejected() -> None:
    limited = model_with(lambda request: httpx.Response(429, text="slow down"))
    with pytest.raises(TransientModelError, match="HTTP 429"):
        complete(limited)
    unauthorized = model_with(
        lambda request: httpx.Response(
            401, json={"error": {"code": 401, "message": "bad key"}}
        )
    )
    with pytest.raises(ModelRequestError, match="bad key"):
        complete(unauthorized)
    return


def test_connection_failure_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(TransientModelError, match="refused"):
        complete(model_with(handler))
    return
