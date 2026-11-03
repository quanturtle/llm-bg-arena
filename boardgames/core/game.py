"""The Game protocol: the one interface every game implements.

Agents, the match runner, logs and the viewer only talk to games through it.
The full contract (determinism, hidden information, simultaneous decisions) is
in docs/ARCHITECTURE.md.
"""

from dataclasses import dataclass
from typing import ClassVar, Protocol

from boardgames.core.actions import ActionSpace
from boardgames.core.decisions import Decision
from boardgames.core.events import Event
from boardgames.core.json_data import JsonObject, JsonValue
from boardgames.core.observation import Observation
from boardgames.core.players import PlayerId
from boardgames.core.scores import Scores


class GameConfig(Protocol):
    """Parameters every game config has; games add their own (map, variant, VP goal)."""

    @property
    def num_players(self) -> int: ...


@dataclass(frozen=True)
class Transition[S]:
    """A new state and the events that produced it."""

    state: S
    events: tuple[Event, ...] = ()


class Game[S, A, C: GameConfig](Protocol):
    """Rules of one game as pure functions over an immutable state `S`.

    `A` is the game's action type and `C` its config type.
    """

    id: ClassVar[str]

    def parse_config(self, raw: JsonObject) -> C:
        """Validated config from JSON; invalid values raise ConfigError."""
        ...

    def config_json(self, config: C) -> dict[str, JsonValue]:
        """Config as JSON, the inverse of `parse_config`."""
        ...

    def setup(self, config: C, seed: int) -> Transition[S]:
        """Initial state; all later randomness comes from the RNG seeded here."""
        ...

    def pending_decisions(self, state: S) -> tuple[Decision, ...]:
        """Open decisions, at most one per player; several are simultaneous."""
        ...

    def legal_actions(self, state: S, decision: Decision) -> ActionSpace[A]:
        """Legal actions for an open decision."""
        ...

    def apply(self, state: S, player: PlayerId, action: A) -> Transition[S]:
        """Answer `player`'s open decision; illegal actions raise IllegalActionError."""
        ...

    def is_terminal(self, state: S) -> bool:
        """Whether the game is over."""
        ...

    def scores(self, state: S) -> Scores:
        """Current points; final points once the state is terminal."""
        ...

    def observe(self, state: S, viewer: PlayerId | None) -> Observation:
        """What `viewer` may see; None is a spectator, who sees public data only."""
        ...

    def render_text(self, observation: Observation) -> str:
        """Compact text of an observation, with a legend, for prompts and the CLI."""
        ...

    def rules_text(self) -> str:
        """Rules summary for LLM players."""
        ...

    def format_action(self, action: A) -> str:
        """Action in text notation; `parse_action` inverts it exactly."""
        ...

    def parse_action(self, text: str) -> A:
        """Strict parse of notation, without legality; bad text raises NotationError."""
        ...

    def describe_action(self, observation: Observation, action: A) -> str:
        """One-line human description of an action, from the deciding player's view."""
        ...

    def action_json(self, action: A) -> dict[str, JsonValue]:
        """Machine form of an action for logs and the viewer."""
        ...
