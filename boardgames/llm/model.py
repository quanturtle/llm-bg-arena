"""The chat model interface the LLM agent talks to, independent of any provider."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from boardgames.core import ArenaError, JsonObject, JsonValue

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
class ModelSettings:
    """Per-model call settings; `model` is an OpenRouter id ("openai/gpt-5-mini")."""

    model: str
    temperature: float | None = None
    max_tokens: int = 1024
    timeout_seconds: float = 120.0
    reasoning_effort: ReasoningEffort | None = None
    seed: int | None = None

    def to_json(self) -> dict[str, JsonValue]:
        """Machine form for logs and cache keys."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "reasoning_effort": self.reasoning_effort,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Completion:
    """A model reply: its text and, when a tool was forced, the raw argument JSON.

    `cost_usd` is None when the provider reported no cost, and 0 for a cached reply.
    """

    text: str
    tool_arguments: str | None
    usage: Usage
    cost_usd: float | None
    api_retries: int = 0
    is_cached: bool = False
    reasoning: str | None = None


class ChatModel(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tool: ToolSpec | None,
    ) -> Completion:
        """One reply; retryable failures raise TransientModelError."""
        ...


def messages_json(messages: Sequence[Message]) -> list[JsonValue]:
    """Messages as JSON, for logs and cache keys."""
    return [{"role": message.role, "content": message.content} for message in messages]
