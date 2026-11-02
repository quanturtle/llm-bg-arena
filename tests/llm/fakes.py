"""A scripted ChatModel for tests."""

from collections.abc import Sequence
from dataclasses import dataclass

from tabletop_arena.llm.model import (
    Completion,
    Message,
    ModelSettings,
    ToolSpec,
    Usage,
)


@dataclass(frozen=True)
class Call:
    messages: tuple[Message, ...]
    settings: ModelSettings
    tool: ToolSpec | None


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
        tool: ToolSpec | None,
    ) -> Completion:
        self.calls.append(Call(tuple(messages), settings, tool))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def reply(
    text: str = "", tool_arguments: str | None = None, cost: float | None = 0.001
) -> Completion:
    return Completion(
        text=text,
        tool_arguments=tool_arguments,
        usage=Usage(prompt_tokens=100, completion_tokens=20),
        cost_usd=cost,
    )
