"""Fakes shared by runner, replay and invariant tests."""

from collections.abc import Sequence

from tabletop_arena.agents import (
    Agent,
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
    Forfeited,
    RandomAgent,
)
from tabletop_arena.core import JsonValue
from tabletop_arena.logs.schema import LogRecord


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
