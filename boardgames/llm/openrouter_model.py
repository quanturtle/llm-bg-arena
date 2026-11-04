"""ChatModel adapter over OpenRouter's chat completions API.

OpenRouter takes one OpenAI-compatible request shape for every model it routes
and returns the dollar cost of each call. Only the HTTP call does I/O: building
the request and reading the response are pure functions.
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

import httpx2
from pydantic import (
    BaseModel,
    BeforeValidator,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)

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
# provider error codes worth retrying, matched whole; any 5xx status is retried too
TRANSIENT_CODES = frozenset(
    {
        "rate_limit_exceeded",
        "server_error",
        "timeout",
        "overloaded",
        "service_unavailable",
        "bad_gateway",
        "gateway_timeout",
    }
)

type FailureKind = Literal["transient", "rejected"]


def missing_if_invalid(value: object, handler: ValidatorFunctionWrapHandler) -> object:
    """The field as validated, or None when a provider sent it in another shape."""
    try:
        return handler(value)
    except ValidationError:
        return None


def arguments_text(value: object) -> object:
    """Tool arguments as JSON text; some providers send the object itself."""
    return json.dumps(value) if isinstance(value, dict) else value


# a field providers fill inconsistently: an unexpected shape reads as missing
type Lenient[T] = Annotated[T | None, WrapValidator(missing_if_invalid)]


class FunctionPayload(BaseModel):
    name: str
    arguments: Annotated[str, BeforeValidator(arguments_text)]


class ToolCallPayload(BaseModel):
    id: Lenient[str] = None
    function: FunctionPayload


class MessagePayload(BaseModel):
    content: Lenient[str] = None
    reasoning: Lenient[str] = None
    tool_calls: list[Lenient[ToolCallPayload]] | None = None


class ChoicePayload(BaseModel):
    message: MessagePayload
    error: Lenient["ErrorPayload"] = None


class UsagePayload(BaseModel):
    prompt_tokens: Lenient[int] = 0
    completion_tokens: Lenient[int] = 0
    cost: Lenient[float] = None


class ErrorPayload(BaseModel):
    code: Lenient[int | str] = None
    message: Lenient[str] = None
    # `raw` here carries the provider's own reason behind "Provider returned error"
    metadata: Lenient[dict[str, object]] = None


class ResponsePayload(BaseModel):
    """The fields of a chat completion response the arena reads."""

    choices: list[ChoicePayload] = []
    usage: Lenient[UsagePayload] = None
    error: Lenient[ErrorPayload] = None


@dataclass(frozen=True)
class UnreadableReply:
    """A response body whose structure did not validate, and the first reason why."""

    reason: str


class OpenRouterChatModel:
    """Sends every completion to OpenRouter; `transport` lets tests fake the network."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx2.AsyncBaseTransport | None = None,
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
                async with httpx2.AsyncClient(
                    base_url=self._base_url,
                    headers=self._headers,
                    transport=self._transport,
                    timeout=settings.timeout_seconds,
                ) as client:
                    response = await client.post("/chat/completions", json=body)
        except (TimeoutError, httpx2.TimeoutException) as error:
            raise TransientModelError(
                f"{settings.model}: no reply within {settings.timeout_seconds}s"
            ) from error
        except httpx2.TransportError as error:
            raise TransientModelError(f"{settings.model}: {error}") from error
        payload = parse_payload(response)
        readable = (
            ResponsePayload() if isinstance(payload, UnreadableReply) else payload
        )
        failed = failure(response.status_code, readable)
        if failed is not None:
            kind, message = failed
            if kind == "transient":
                raise TransientModelError(f"{settings.model}: {message}")
            raise ModelRequestError(f"{settings.model}: {message}")
        if isinstance(payload, UnreadableReply):
            raise TransientModelError(
                f"{settings.model}: unreadable reply: {payload.reason}"
            )
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


def parse_payload(response: httpx2.Response) -> ResponsePayload | UnreadableReply:
    """The response body; a field in an unexpected shape reads as missing.

    A body that is not JSON counts as empty; a broken structure is unreadable.
    """
    try:
        raw = clean_json(response.json())
    except (ValueError, UnicodeError):
        return ResponsePayload()
    try:
        return ResponsePayload.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        place = ".".join(str(part) for part in first["loc"]) or "body"
        return UnreadableReply(f"{place}: {first['msg']}")


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
    """Whether the HTTP status or the provider's error code is worth retrying."""
    if status in TRANSIENT_STATUSES or status >= 500:
        return True
    if isinstance(code, int):
        return code in TRANSIENT_STATUSES or code >= 500
    text = code.strip().lower()
    if text.isdigit():
        return transient_code(int(text), status)
    return text in TRANSIENT_CODES


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
            if call is not None
        ),
        usage=Usage(usage.prompt_tokens or 0, usage.completion_tokens or 0),
        cost_usd=usage.cost,
        reasoning=message.reasoning,
    )
