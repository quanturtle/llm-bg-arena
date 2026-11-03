"""A scripted ChatModel for tests."""

from collections.abc import Sequence
from dataclasses import dataclass

from boardgames.llm.model import (
    Completion,
    Message,
    ModelSettings,
    ToolCall,
    ToolChoice,
    ToolSpec,
    Usage,
)

SUBMIT_TOOL = "submit_action"


@dataclass(frozen=True)
class Call:
    messages: tuple[Message, ...]
    settings: ModelSettings
    tools: tuple[ToolSpec, ...]
    tool_choice: ToolChoice


class QueuedChatModel:
    """Returns or raises the queued outcomes in order and records every call."""

    def __init__(self, outcomes: Sequence[Completion | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[Call] = []
        return

    async def complete(
        self,
        messages: Sequence[Message],
        settings: ModelSettings,
        tools: Sequence[ToolSpec],
        tool_choice: ToolChoice,
    ) -> Completion:
        self.calls.append(Call(tuple(messages), settings, tuple(tools), tool_choice))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def reply(
    text: str = "",
    tool_arguments: str | None = None,
    cost: float | None = 0.001,
    reasoning: str | None = None,
) -> Completion:
    """A reply with text, or with one submit_action call when given arguments."""
    calls = (
        ()
        if tool_arguments is None
        else (ToolCall("call_1", SUBMIT_TOOL, tool_arguments),)
    )
    return tool_calls_reply(calls, text=text, cost=cost, reasoning=reasoning)


def tool_calls_reply(
    calls: Sequence[ToolCall],
    text: str = "",
    cost: float | None = 0.001,
    reasoning: str | None = None,
) -> Completion:
    """A reply that makes the given tool calls."""
    return Completion(
        text=text,
        tool_calls=tuple(calls),
        usage=Usage(prompt_tokens=100, completion_tokens=20),
        cost_usd=cost,
        reasoning=reasoning,
    )
