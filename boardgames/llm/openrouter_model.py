"""ChatModel adapter over OpenRouter's chat completions API.

OpenRouter takes one OpenAI-compatible request shape for every model it routes
and returns the dollar cost of each call. Only the HTTP call does I/O: building
the request and reading the response are pure functions.
"""

import asyncio
from collections.abc import Sequence
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from boardgames.core import JsonValue, clean_json
from boardgames.llm.model import (
    Completion,
    Message,
    ModelRequestError,
    ModelSettings,
    ToolCall,
    ToolChoice,
    ToolSpec,
    TransientModelError,
    Usage,
    messages_json,
    tool_choice_json,
    tools_json,
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
TRANSIENT_STATUSES = frozenset({408, 429})

type FailureKind = Literal["transient", "rejected"]


class FunctionPayload(BaseModel):
    name: str
    arguments: str


class ToolCallPayload(BaseModel):
    id: str | None = None
    function: FunctionPayload


class MessagePayload(BaseModel):
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolCallPayload] | None = None


class ChoicePayload(BaseModel):
    message: MessagePayload
    error: "ErrorPayload | None" = None


class UsagePayload(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None


class ErrorPayload(BaseModel):
    code: int | str | None = None
    message: str | None = None
    # `raw` here carries the provider's own reason behind "Provider returned error"
    metadata: dict[str, object] | None = None


class ResponsePayload(BaseModel):
    """The fields of a chat completion response the arena reads."""

    choices: list[ChoicePayload] = []
    usage: UsagePayload | None = None
    error: ErrorPayload | None = None


class OpenRouterChatModel:
    """Sends every completion to OpenRouter; `transport` lets tests fake the network."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._transport = transport
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Title": "boardgames",
        }
        return

    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tools: Sequence[ToolSpec],
        tool_choice: ToolChoice,
    ) -> Completion:
        body = request_body(messages, settings, tools, tool_choice)
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    headers=self._headers,
                    transport=self._transport,
                    timeout=settings.timeout_seconds,
                ) as client:
                    response = await client.post("/chat/completions", json=body)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise TransientModelError(
                f"{settings.model}: no reply within {settings.timeout_seconds}s"
            ) from error
        except httpx.TransportError as error:
            raise TransientModelError(f"{settings.model}: {error}") from error
        payload = parse_payload(response)
        failed = failure(response.status_code, payload)
        if failed is not None:
            kind, message = failed
            if kind == "transient":
                raise TransientModelError(f"{settings.model}: {message}")
            raise ModelRequestError(f"{settings.model}: {message}")
        return completion_from(payload, settings.model)


def request_body(
    messages: Sequence[Message],
    settings: ModelSettings,
    tools: Sequence[ToolSpec],
    tool_choice: ToolChoice,
) -> dict[str, JsonValue]:
    """The chat completion request; unset options and empty tool lists are left out."""
    body: dict[str, JsonValue] = {
        "model": settings.model,
        "messages": messages_json(messages),
        "max_tokens": settings.max_tokens,
        "usage": {"include": True},
    }
    if settings.temperature is not None:
        body["temperature"] = settings.temperature
    if settings.top_p is not None:
        body["top_p"] = settings.top_p
    if settings.seed is not None:
        body["seed"] = settings.seed
    reasoning = reasoning_json(settings)
    if reasoning:
        body["reasoning"] = reasoning
    if settings.verbosity is not None:
        body["verbosity"] = settings.verbosity
    if tools:
        body["tools"] = tools_json(tools)
        body["tool_choice"] = tool_choice_json(tool_choice)
    body.update(settings.extra)
    return body


def reasoning_json(settings: ModelSettings) -> dict[str, JsonValue]:
    """OpenRouter's reasoning object: `enabled`, `effort` and `max_tokens` when set."""
    reasoning: dict[str, JsonValue] = {}
    if settings.reasoning is not None:
        reasoning["enabled"] = settings.reasoning
    if settings.reasoning_effort is not None:
        reasoning["effort"] = settings.reasoning_effort
    if settings.thinking_budget_tokens is not None:
        reasoning["max_tokens"] = settings.thinking_budget_tokens
    return reasoning


def parse_payload(response: httpx.Response) -> ResponsePayload:
    """The response body, keeping every field it can read.

    A body that is not a JSON object counts as empty. One wrongly typed field
    (a null tool-call id, a string error code) must not throw away the rest of
    the reply, including its usage and cost.
    """
    try:
        raw = clean_json(response.json())
    except (ValueError, UnicodeError):
        return ResponsePayload()
    if not isinstance(raw, dict):
        return ResponsePayload()
    try:
        return ResponsePayload.model_validate(raw)
    except ValidationError:
        return salvage_payload(raw)


def salvage_payload(raw: dict[str, object]) -> ResponsePayload:
    """Read the known fields of a response that did not validate as a whole."""
    choices = raw.get("choices")
    salvaged = [
        salvage_choice(choice)
        for choice in choices
        if isinstance(choice, dict)
    ] if isinstance(choices, list) else []
    return ResponsePayload(
        choices=salvaged,
        usage=salvage_usage(raw.get("usage")),
        error=salvage_error(raw.get("error")),
    )


def salvage_choice(raw: dict[str, object]) -> ChoicePayload:
    message = raw.get("message")
    data = message if isinstance(message, dict) else {}
    calls = data.get("tool_calls")
    return ChoicePayload(
        message=MessagePayload(
            content=optional_string(data.get("content")),
            reasoning=optional_string(data.get("reasoning")),
            tool_calls=[
                call
                for call in (
                    salvage_tool_call(call)
                    for call in calls
                    if isinstance(call, dict)
                )
                if call is not None
            ] if isinstance(calls, list) else None,
        ),
        error=salvage_error(raw.get("error")),
    )


def salvage_tool_call(raw: dict[str, object]) -> ToolCallPayload | None:
    function = raw.get("function")
    data = function if isinstance(function, dict) else {}
    name = optional_string(data.get("name"))
    arguments = optional_string(data.get("arguments"))
    if name is None or arguments is None:
        return None
    return ToolCallPayload(
        id=optional_string(raw.get("id")),
        function=FunctionPayload(name=name, arguments=arguments),
    )


def salvage_usage(raw: object) -> UsagePayload | None:
    if not isinstance(raw, dict):
        return None
    return UsagePayload(
        prompt_tokens=optional_int(raw.get("prompt_tokens")) or 0,
        completion_tokens=optional_int(raw.get("completion_tokens")) or 0,
        cost=optional_number(raw.get("cost")),
    )


def salvage_error(raw: object) -> ErrorPayload | None:
    if not isinstance(raw, dict):
        return None
    code = raw.get("code")
    metadata = raw.get("metadata")
    known_code = (
        code
        if isinstance(code, int | str) and not isinstance(code, bool)
        else None
    )
    return ErrorPayload(
        code=known_code,
        message=optional_string(raw.get("message")),
        metadata=dict(metadata) if isinstance(metadata, dict) else None,
    )


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def optional_number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def failure(status: int, payload: ResponsePayload) -> tuple[FailureKind, str] | None:
    """What went wrong, from the HTTP status or an error object in the body.

    The error object may sit at the top level or inside the first choice.
    """
    error = payload.error
    if error is None and payload.choices:
        error = payload.choices[0].error
    if status < 400 and error is None:
        return None
    code: int | str = status
    message = f"HTTP {status}"
    if error is not None:
        code = error.code if error.code is not None else code
        message = error.message or message
        raw = (error.metadata or {}).get("raw")
        if isinstance(raw, str) and raw:
            message = f"{message}: {raw}"
    if transient_code(code, status):
        return "transient", message
    return "rejected", message


def transient_code(code: int | str, status: int) -> bool:
    """Whether a status or provider error code is worth retrying."""
    if isinstance(code, int):
        return code in TRANSIENT_STATUSES or code >= 500
    text = code.lower()
    if text.isdigit():
        return transient_code(int(text), status)
    return any(
        word in text
        for word in (
            "rate",
            "limit",
            "timeout",
            "unavailable",
            "overload",
            "temporar",
            "server",
        )
    )


def completion_from(payload: ResponsePayload, model: str) -> Completion:
    """Completion from a successful response; a reply without choices is rejected."""
    if not payload.choices:
        raise ModelRequestError(f"{model}: the reply has no choices")
    message = payload.choices[0].message
    usage = payload.usage or UsagePayload()
    return Completion(
        text=message.content or "",
        tool_calls=tuple(
            ToolCall(
                call.id or f"call_{index}", call.function.name, call.function.arguments
            )
            for index, call in enumerate(message.tool_calls or ())
        ),
        usage=Usage(usage.prompt_tokens, usage.completion_tokens),
        cost_usd=usage.cost,
        reasoning=message.reasoning,
    )
