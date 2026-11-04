"""Fakes shared by runner, replay and invariant tests."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from boardgames.agents import (
    Agent,
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
    Forfeited,
    RandomAgent,
)
from boardgames.core import (
    ActionSpace,
    Decision,
    FlatActionSpace,
    IllegalActionError,
    JsonObject,
    JsonValue,
    NotationError,
    Observation,
    PlayerId,
    Scores,
    Transition,
)
from boardgames.logs.schema import LogRecord


class MemorySink:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []
        return

    def write(self, record: LogRecord) -> None:
        self.records.append(record)
        return


class FakeClock:
    """Each monotonic() call advances half a second; timestamps are fixed."""

    def __init__(self) -> None:
        self._now = 0.0
        return

    def monotonic(self) -> float:
        self._now += 0.5
        return self._now

    def now_iso(self) -> str:
        return "2026-01-01T00:00:00+00:00"


class ScriptedAgent:
    """Plays the given notations in order."""

    def __init__(self, moves: Sequence[str]) -> None:
        self._moves = list(moves)
        return

    @property
    def name(self) -> str:
        return "scripted"

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "scripted"}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        action = request.action_text.parse_action(self._moves.pop(0))
        return Chosen(action, DecisionTrace())


class RecordingAgent:
    """Random play that keeps every request it receives."""

    def __init__(self, seed: int) -> None:
        self._inner = RandomAgent(seed)
        self.requests: list[DecisionRequest[object]] = []
        return

    @property
    def name(self) -> str:
        return "recording"

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "recording"}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        self.requests.append(request)  # type: ignore[arg-type]
        return await self._inner.decide(request)


class ForfeitingAgent:
    @property
    def name(self) -> str:
        return "quitter"

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "quitter"}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        return Forfeited("gave up", DecisionTrace(illegal_attempts=3))


class FixedAgent:
    """Always proposes the same notation, legal or not."""

    def __init__(self, notation: str) -> None:
        self._notation = notation
        return

    @property
    def name(self) -> str:
        return "fixed"

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "fixed"}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        return Chosen(request.action_text.parse_action(self._notation), DecisionTrace())


def random_agents(count: int, seed: int = 0) -> list[Agent]:
    return [RandomAgent(seed * 100 + seat) for seat in range(count)]


TOKENS = ("a", "b", "c")


@dataclass(frozen=True)
class ClaimConfig:
    num_players: int = 2


@dataclass(frozen=True)
class ClaimState:
    """`claims[p]` is the token seat p took, or None while it still decides."""

    claims: tuple[str | None, ...]


class TokenClaim:
    """Every seat claims a free token at the same time, so two can clash."""

    id: ClassVar[str] = "token_claim"

    def parse_config(self, raw: JsonObject) -> ClaimConfig:
        return ClaimConfig()

    def config_json(self, config: ClaimConfig) -> dict[str, JsonValue]:
        return {"num_players": config.num_players}

    def setup(self, config: ClaimConfig, seed: int) -> Transition[ClaimState]:
        return Transition(ClaimState((None,) * config.num_players), ())

    def pending_decisions(self, state: ClaimState) -> tuple[Decision, ...]:
        return tuple(
            Decision(PlayerId(seat), "claim", "Claim a free token.")
            for seat, claim in enumerate(state.claims)
            if claim is None
        )

    def legal_actions(self, state: ClaimState, decision: Decision) -> ActionSpace[str]:
        return FlatActionSpace(free_tokens(state), str)

    def apply(
        self, state: ClaimState, player: PlayerId, action: str
    ) -> Transition[ClaimState]:
        if action not in free_tokens(state):
            raise IllegalActionError(f"P{player + 1} cannot claim {action}")
        claims = tuple(
            action if seat == player else claim
            for seat, claim in enumerate(state.claims)
        )
        return Transition(ClaimState(claims), ())

    def is_terminal(self, state: ClaimState) -> bool:
        return all(claim is not None for claim in state.claims)

    def scores(self, state: ClaimState) -> Scores:
        return Scores({PlayerId(seat): 1.0 for seat in range(len(state.claims))})

    def public_scores(self, state: ClaimState) -> Scores:
        return self.scores(state)

    def observe(self, state: ClaimState, viewer: PlayerId | None) -> Observation:
        return Observation(viewer, {"claims": list(state.claims)})

    def render_text(self, observation: Observation) -> str:
        return str(observation.data)

    def rules_text(self) -> str:
        return "Claim one free token."

    def format_action(self, action: str) -> str:
        return action

    def parse_action(self, text: str) -> str:
        if text not in TOKENS:
            raise NotationError(f"{text!r} is not a token")
        return text

    def describe_action(self, observation: Observation, action: str) -> str:
        return f"Claim {action}"

    def action_json(self, action: str) -> dict[str, JsonValue]:
        return {"token": action}


def free_tokens(state: ClaimState) -> list[str]:
    return [token for token in TOKENS if token not in state.claims]
