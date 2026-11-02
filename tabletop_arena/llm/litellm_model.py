"""ChatModel adapter over LiteLLM, which reaches Anthropic, OpenAI, OpenRouter and more.

LiteLLM reads provider keys (ANTHROPIC_API_KEY, OPENROUTER_API_KEY, ...) from the
environment itself.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from tabletop_arena.llm.model import (
    Completion,
    Message,
    ModelRequestError,
    ModelSettings,
    TokenPrices,
    ToolSpec,
    TransientModelError,
    Usage,
    cost_usd,
    messages_json,
)

TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    RateLimitError,
    Timeout,
    APIConnectionError,
    InternalServerError,
    ServiceUnavailableError,
)
REJECTED_ERRORS: tuple[type[Exception], ...] = (
    BadRequestError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)


class LiteLLMChatModel:
    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tool: ToolSpec | None,
    ) -> Completion:
        try:
            response = await litellm.acompletion(
                **request_arguments(messages, settings, tool)
            )
        except TRANSIENT_ERRORS as error:
            raise TransientModelError(f"{settings.model}: {error}") from error
        except REJECTED_ERRORS as error:
            raise ModelRequestError(f"{settings.model}: {error}") from error
        prices = settings.prices or table_prices(settings.model, litellm.model_cost)
        return completion_from(response, prices)


def request_arguments(
    messages: Sequence[Message], settings: ModelSettings, tool: ToolSpec | None
) -> dict[str, Any]:
    """Keyword arguments for litellm.acompletion; unset options are left out."""
    arguments: dict[str, Any] = {
        "model": settings.model,
        "messages": messages_json(messages),
        "max_tokens": settings.max_tokens,
        "timeout": settings.timeout_seconds,
    }
    if settings.temperature is not None:
        arguments["temperature"] = settings.temperature
    if settings.reasoning_effort is not None:
        arguments["reasoning_effort"] = settings.reasoning_effort
    if settings.seed is not None:
        arguments["seed"] = settings.seed
    if tool is not None:
        arguments["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
        ]
        arguments["tool_choice"] = {"type": "function", "function": {"name": tool.name}}
    return arguments


def table_prices(
    model: str, table: Mapping[str, Mapping[str, Any]]
) -> TokenPrices | None:
    """Prices from LiteLLM's table, trying the id without provider prefixes too."""
    parts = model.split("/")
    for start in range(len(parts)):
        entry = table.get("/".join(parts[start:]), {})
        input_cost = entry.get("input_cost_per_token")
        output_cost = entry.get("output_cost_per_token")
        if input_cost is not None and output_cost is not None:
            return TokenPrices(input_cost * 1_000_000, output_cost * 1_000_000)
    return None


def completion_from(response: Any, prices: TokenPrices | None) -> Completion:
    """Completion from a LiteLLM response object."""
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    usage = Usage(
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
    )
    return Completion(
        text=message.content or "",
        tool_arguments=tool_calls[0].function.arguments if tool_calls else None,
        usage=usage,
        cost_usd=cost_usd(usage, prices),
    )
