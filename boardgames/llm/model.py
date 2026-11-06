"""The chat model interface the LLM agent talks to, independent of any provider."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from boardgames.core import ArenaError, ConfigError, JsonObject, JsonValue

type Role = Literal["system", "user", "assistant", "tool"]
# OpenRouter's reasoning.effort levels, least first; reasoning: false turns it off
type ReasoningEffort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
# OpenRouter's top-level verbosity: answer length; on Claude, Anthropic's own effort
type Verbosity = Literal["low", "medium", "high", "xhigh", "max"]


class TransientModelError(ArenaError):
    """A model call failed in a way worth retrying: rate limit, timeout, outage."""


class ModelUnavailableError(ArenaError):
    """A model call still failed after every retry."""


class ModelRequestError(ArenaError):
    """The provider rejected the request: bad key, unknown model, invalid input."""


@dataclass(frozen=True)
class ToolCall:
    """One call the model made; `arguments` is the raw JSON text it produced."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Message:
    """A turn; assistant turns may carry tool calls, tool turns answer one by id."""

    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may call; its arguments follow `parameters`."""

    name: str
    description: str
    parameters: JsonObject


@dataclass(frozen=True)
class ForcedTool:
    """The model must call this one tool."""

    name: str


type ToolChoice = Literal["auto", "required"] | ForcedTool


def reasoning_conflict(
    reasoning: bool | None,
    effort: ReasoningEffort | None,
    budget: int | None,
) -> str | None:
    """Why these reasoning settings cannot go together, or None when they can."""
    if effort is not None and budget is not None:
        return "set reasoning_effort or thinking_budget_tokens, not both"
    if reasoning is False and (effort is not None or budget is not None):
        return "reasoning is false, so drop reasoning_effort and thinking_budget_tokens"
    return None


@dataclass(frozen=True)
class ModelSettings:
    """Per-model call settings; `model` is an OpenRouter id ("openai/gpt-5-mini").

    Thinking takes an effort or a token budget, not both, and neither when it is off.
    """

    model: str
    temperature: float | None = None
    top_p: float | None = None
    # also covers a thinking model's reasoning
    max_tokens: int = 4096
    timeout_seconds: float = 120.0
    # turns thinking on or off; None keeps the model's default
    reasoning: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    thinking_budget_tokens: int | None = None
    # answer length, a separate request field
    verbosity: Verbosity | None = None
    seed: int | None = None
    # merged into the request body as is, for provider routing and other options
    extra: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        problem = reasoning_conflict(
            self.reasoning, self.reasoning_effort, self.thinking_budget_tokens
        )
        if problem is not None:
            raise ConfigError(f"{self.model}: {problem}")
        return

    def to_json(self) -> dict[str, JsonValue]:
        """Machine form for logs and cache keys."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "reasoning": self.reasoning,
            "reasoning_effort": self.reasoning_effort,
            "thinking_budget_tokens": self.thinking_budget_tokens,
            "verbosity": self.verbosity,
            "seed": self.seed,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Completion:
    """A model reply: its text and the tool calls it made.

    `cost_usd` is None when the provider reported no cost, and 0 for a cached reply.
    """

    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    cost_usd: float | None
    api_retries: int = 0
    is_cached: bool = False
    reasoning: str | None = None

    @property
    def tool_arguments(self) -> str | None:
        """Arguments of the first tool call, the reply when one tool was forced."""
        return self.tool_calls[0].arguments if self.tool_calls else None


class ChatModel(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tools: Sequence[ToolSpec],
        tool_choice: ToolChoice,
    ) -> Completion:
        """One reply; retryable failures raise TransientModelError."""
        ...


def messages_json(messages: Sequence[Message]) -> list[JsonValue]:
    """Messages as JSON for requests, logs and cache keys; tool fields only when set."""
    return [message_json(message) for message in messages]


def message_json(message: Message) -> dict[str, JsonValue]:
    """One message in the chat completions shape."""
    data: dict[str, JsonValue] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        data["tool_calls"] = [tool_call_json(call) for call in message.tool_calls]
    if message.tool_call_id is not None:
        data["tool_call_id"] = message.tool_call_id
    return data


def tool_call_json(call: ToolCall) -> dict[str, JsonValue]:
    """A tool call in the chat completions shape."""
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": call.arguments},
    }


def tools_json(tools: Sequence[ToolSpec]) -> list[JsonValue]:
    """Tools in the chat completions function-tool shape."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def tool_choice_json(choice: ToolChoice) -> JsonValue:
    """A tool choice in the chat completions shape."""
    if isinstance(choice, ForcedTool):
        return {"type": "function", "function": {"name": choice.name}}
    return choice
