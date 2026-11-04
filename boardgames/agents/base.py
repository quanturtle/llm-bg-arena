"""The agent interface: every player type answers a DecisionRequest the same way."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from boardgames.agents.attempt import AttemptRecord
from boardgames.core import (
    ActionSpace,
    Decision,
    Event,
    JsonValue,
    Observation,
)

type FallbackPolicy = Literal["forfeit", "random", "default"]


class ActionText[A](Protocol):
    """The game's action notation, which every Game provides."""

    def format_action(self, action: A) -> str: ...

    def parse_action(self, text: str) -> A: ...

    def describe_action(self, observation: Observation, action: A) -> str: ...


def ignore_unfinished(trace: "DecisionTrace") -> None:
    """Drop the trace of a decision cut short, for requests made outside a match."""
    return


@dataclass(frozen=True)
class DecisionRequest[A]:
    """What an agent may use to choose, built only from the player's own view.

    `recent_events` are the events this player could see since their last decision.
    """

    game_id: str
    decision: Decision
    observation: Observation
    observation_text: str
    actions: ActionSpace[A]
    recent_events: tuple[Event, ...]
    rules: str
    action_text: ActionText[A]
    # takes the model calls already paid for when a failure or a stop cuts the
    # decision short, so the runner can log their cost
    record_unfinished: Callable[["DecisionTrace"], None] = field(
        default=ignore_unfinished, compare=False, repr=False
    )


@dataclass(frozen=True)
class DecisionTrace:
    """How an agent reached its choice, logged with the decision.

    `attempts` holds agent-specific detail, such as each model call of an LLM agent.
    """

    reasoning: str | None = None
    memory: str | None = None
    attempts: tuple[AttemptRecord, ...] = ()
    illegal_attempts: int = 0
    api_retries: int = 0
    fallback: FallbackPolicy | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = 0.0

    def to_json(self) -> dict[str, JsonValue]:
        """Machine form for logs."""
        return {
            "reasoning": self.reasoning,
            "memory": self.memory,
            "attempts": [attempt.model_dump(mode="json") for attempt in self.attempts],
            "illegal_attempts": self.illegal_attempts,
            "api_retries": self.api_retries,
            "fallback": self.fallback,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
        }


@dataclass(frozen=True)
class Chosen[A]:
    """The agent picked a legal action."""

    action: A
    trace: DecisionTrace


@dataclass(frozen=True)
class Forfeited:
    """The agent gave up the game, for example after running out of retries."""

    reason: str
    trace: DecisionTrace


type AgentChoice[A] = Chosen[A] | Forfeited


class Agent(Protocol):
    """A player. One instance plays one seat for one match, so it may keep memory."""

    @property
    def name(self) -> str:
        """Short label for logs and leaderboards, such as "random" or a model name."""
        ...

    def settings(self) -> dict[str, JsonValue]:
        """Configuration recorded in the match log."""
        ...

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        """Choose an action for `request.decision`; a Chosen action must be legal."""
        ...
