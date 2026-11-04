import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from boardgames.core import ConfigError, JsonValue
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
        model="openai/gpt-x",
        temperature=0.2,
        reasoning_effort="minimal",
        verbosity="low",
        seed=4,
    )
    body = request_body(MESSAGES, settings, (), "auto")
    assert (body["temperature"], body["seed"]) == (0.2, 4)
    assert body["reasoning"] == {"effort": "minimal"}
    assert body["verbosity"] == "low"
    assert "tools" not in body
    assert "tool_choice" not in body
    return


def test_request_body_passes_top_p_and_a_thinking_budget() -> None:
    settings = ModelSettings(model="m", top_p=0.9, thinking_budget_tokens=2048)
    body = request_body(MESSAGES, settings, (), "auto")
    assert body["top_p"] == 0.9
    assert body["reasoning"] == {"max_tokens": 2048}
    return


def test_reasoning_false_turns_thinking_off() -> None:
    settings = ModelSettings(model="m", reasoning=False)
    assert request_body(MESSAGES, settings, (), "auto")["reasoning"] == {
        "enabled": False
    }
    return


def test_reasoning_and_effort_are_sent_as_separate_fields() -> None:
    settings = ModelSettings(model="m", reasoning=True, reasoning_effort="high")
    assert request_body(MESSAGES, settings, (), "auto")["reasoning"] == {
        "enabled": True,
        "effort": "high",
    }
    return


def test_request_body_merges_extra_last_so_it_overrides_built_in_fields() -> None:
    extra: dict[str, JsonValue] = {"provider": {"order": ["openai"]}, "max_tokens": 5}
    body = request_body(MESSAGES, ModelSettings(model="m", extra=extra), (), "auto")
    assert body["provider"] == {"order": ["openai"]}
    assert body["max_tokens"] == 5
    return


def test_effort_and_budget_together_are_a_config_error() -> None:
    with pytest.raises(ConfigError, match="not both"):
        ModelSettings(model="m", reasoning_effort="low", thinking_budget_tokens=1)
    return


def test_effort_with_reasoning_off_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="reasoning is false"):
        ModelSettings(model="m", reasoning=False, reasoning_effort="low")
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


def test_a_null_tool_call_id_keeps_the_reply_and_its_cost() -> None:
    payload = reply_payload(content=None)
    payload["choices"][0]["message"]["tool_calls"] = [  # type: ignore[index]
        {
            "id": None,
            "function": {"name": "submit_action", "arguments": '{"action": "b2"}'},
        }
    ]
    completion = complete(
        model_with(lambda request: httpx.Response(200, json=payload))
    )
    assert completion.tool_calls == (
        ToolCall("call_0", "submit_action", '{"action": "b2"}'),
    )
    assert completion.cost_usd == pytest.approx(0.0015)
    return


def test_a_string_error_code_is_read_and_rate_limits_are_transient() -> None:
    body = {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}
    with pytest.raises(TransientModelError, match="slow down"):
        complete(model_with(lambda request: httpx.Response(200, json=body)))
    return


def test_a_5xx_is_retried_whatever_its_code_and_unknown_codes_are_not() -> None:
    gateway = {"error": {"code": "bad_gateway", "message": "upstream died"}}
    with pytest.raises(TransientModelError, match="upstream died"):
        complete(model_with(lambda request: httpx.Response(502, json=gateway)))
    limit = {"error": {"code": "key_limit_exceeded", "message": "out of credit"}}
    with pytest.raises(ModelRequestError, match="out of credit"):
        complete(model_with(lambda request: httpx.Response(200, json=limit)))
    return


def test_tool_arguments_sent_as_an_object_are_kept_as_text() -> None:
    payload = reply_payload(content=None)
    payload["choices"][0]["message"]["tool_calls"] = [  # type: ignore[index]
        {
            "id": "c1",
            "function": {"name": "submit_action", "arguments": {"action": "b2"}},
        }
    ]
    completion = complete(model_with(lambda request: httpx.Response(200, json=payload)))
    assert completion.tool_calls == (
        ToolCall("c1", "submit_action", '{"action": "b2"}'),
    )
    return


def test_one_bad_usage_field_does_not_throw_away_the_reply() -> None:
    payload = reply_payload()
    payload["usage"] = {"prompt_tokens": "many", "completion_tokens": 100}
    completion = complete(
        model_with(lambda request: httpx.Response(200, json=payload))
    )
    assert completion.text == "b2"
    assert completion.cost_usd is None
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
    upstream = ResponsePayload.model_validate(
        {
            "error": {
                "code": 429,
                "message": "Provider returned error",
                "metadata": {"raw": "rate-limited upstream"},
            }
        }
    )
    assert failure(429, upstream) == (
        "transient",
        "Provider returned error: rate-limited upstream",
    )
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


def test_timeout_bounds_the_whole_call_not_each_read() -> None:
    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(
            self, request: httpx.Request
        ) -> httpx.Response:
            await asyncio.sleep(0.2)
            return httpx.Response(200, json=reply_payload(), request=request)

    model = OpenRouterChatModel("test-key", transport=SlowTransport())
    settings = ModelSettings(model="m", timeout_seconds=0.05)
    with pytest.raises(TransientModelError, match=r"no reply within 0\.05s"):
        asyncio.run(model.complete(MESSAGES, settings, (), "auto"))
    return


def test_connection_failure_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(TransientModelError, match="refused"):
        complete(model_with(handler))
    return


def test_an_error_inside_the_choice_is_a_failure() -> None:
    body = {"choices": [{"message": {}, "error": {"code": 502, "message": "down"}}]}
    with pytest.raises(TransientModelError, match="down"):
        complete(model_with(lambda request: httpx.Response(200, json=body)))
    return


def test_tool_calls_without_ids_get_distinct_ids() -> None:
    payload = reply_payload(content=None)
    payload["choices"][0]["message"]["tool_calls"] = [  # type: ignore[index]
        {"function": {"name": "get_state", "arguments": "{}"}},
        {"function": {"name": "get_rules", "arguments": "{}"}},
    ]
    completion = completion_from(ResponsePayload.model_validate(payload), "m")
    assert [call.id for call in completion.tool_calls] == ["call_0", "call_1"]
    return
