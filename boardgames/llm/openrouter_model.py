"""ChatModel adapter over OpenRouter's chat completions API.

OpenRouter takes one OpenAI-compatible request shape for every model it routes
and returns the dollar cost of each call. Only the HTTP call does I/O: building
the request and reading the response are pure functions.
"""

from collections.abc import Sequence
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from boardgames.core import JsonValue
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
    id: str = ""
    function: FunctionPayload


class MessagePayload(BaseModel):
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolCallPayload] | None = None


class ChoicePayload(BaseModel):
    message: MessagePayload


class UsagePayload(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float | None = None


class ErrorPayload(BaseModel):
    code: int | None = None
    message: str | None = None


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
            "X-Title": "tabletop-arena",
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
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                transport=self._transport,
                timeout=settings.timeout_seconds,
            ) as client:
                response = await client.post("/chat/completions", json=body)
        except httpx.TimeoutException as error:
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
    if settings.reasoning_effort is not None:
        body["reasoning"] = {"effort": settings.reasoning_effort}
    if settings.thinking_budget_tokens is not None:
        body["reasoning"] = {"max_tokens": settings.thinking_budget_tokens}
    if tools:
        body["tools"] = tools_json(tools)
        body["tool_choice"] = tool_choice_json(tool_choice)
    body.update(settings.extra)
    return body


def parse_payload(response: httpx.Response) -> ResponsePayload:
    """The response body; a body that is not a JSON object counts as empty."""
    try:
        return ResponsePayload.model_validate(response.json())
    except (ValueError, ValidationError):
        return ResponsePayload()


def failure(status: int, payload: ResponsePayload) -> tuple[FailureKind, str] | None:
    """What went wrong, from the HTTP status or an error object in the body."""
    if status < 400 and payload.error is None:
        return None
    code, message = status, f"HTTP {status}"
    if payload.error is not None:
        code = payload.error.code if payload.error.code is not None else code
        message = payload.error.message or message
    if code in TRANSIENT_STATUSES or code >= 500:
        return "transient", message
    return "rejected", message


def completion_from(payload: ResponsePayload, model: str) -> Completion:
    """Completion from a successful response; a reply without choices is rejected."""
    if not payload.choices:
        raise ModelRequestError(f"{model}: the reply has no choices")
    message = payload.choices[0].message
    usage = payload.usage or UsagePayload()
    return Completion(
        text=message.content or "",
        tool_calls=tuple(
            ToolCall(call.id, call.function.name, call.function.arguments)
            for call in message.tool_calls or ()
        ),
        usage=Usage(usage.prompt_tokens, usage.completion_tokens),
        cost_usd=usage.cost,
        reasoning=message.reasoning,
    )
