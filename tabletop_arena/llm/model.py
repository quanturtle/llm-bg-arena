"""The chat model interface the LLM agent talks to, independent of any provider."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from tabletop_arena.core import ArenaError, JsonObject, JsonValue

type Role = Literal["system", "user", "assistant"]
type ReasoningEffort = Literal["low", "medium", "high"]


class TransientModelError(ArenaError):
    """A model call failed in a way worth retrying: rate limit, timeout, outage."""


class ModelUnavailableError(ArenaError):
    """A model call still failed after every retry."""


class ModelRequestError(ArenaError):
    """The provider rejected the request: bad key, unknown model, invalid input."""


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class ToolSpec:
    """A function the model is forced to call; its arguments carry the answer."""

    name: str
    description: str
    parameters: JsonObject


@dataclass(frozen=True)
class TokenPrices:
    input_per_million: float
    output_per_million: float


@dataclass(frozen=True)
class ModelSettings:
    """Per-model call settings; `model` is a LiteLLM id ("anthropic/claude-haiku-5-5").

    `prices` overrides the provider price table for cost accounting.
    """

    model: str
    temperature: float | None = None
    max_tokens: int = 1024
    timeout_seconds: float = 120.0
    reasoning_effort: ReasoningEffort | None = None
    seed: int | None = None
    prices: TokenPrices | None = None

    def to_json(self) -> dict[str, JsonValue]:
        """Machine form for logs and cache keys."""
        prices: JsonValue = None
        if self.prices is not None:
            prices = {
                "input_per_million": self.prices.input_per_million,
                "output_per_million": self.prices.output_per_million,
            }
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "reasoning_effort": self.reasoning_effort,
            "seed": self.seed,
            "prices": prices,
        }


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Completion:
    """A model reply: its text and, when a tool was forced, the raw argument JSON.

    `cost_usd` is None when the price is unknown, and 0 for a cached reply.
    """

    text: str
    tool_arguments: str | None
    usage: Usage
    cost_usd: float | None
    api_retries: int = 0
    is_cached: bool = False


class ChatModel(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tool: ToolSpec | None,
    ) -> Completion:
        """One reply; retryable failures raise TransientModelError."""
        ...


def cost_usd(usage: Usage, prices: TokenPrices | None) -> float | None:
    """Dollar cost of a call, or None when prices are unknown."""
    if prices is None:
        return None
    return (
        usage.prompt_tokens * prices.input_per_million
        + usage.completion_tokens * prices.output_per_million
    ) / 1_000_000


def messages_json(messages: Sequence[Message]) -> list[JsonValue]:
    """Messages as JSON, for logs and cache keys."""
    return [{"role": message.role, "content": message.content} for message in messages]
