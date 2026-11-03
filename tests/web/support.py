"""Logs on disk for store, timeline and app tests."""

import asyncio
from collections.abc import Sequence
from pathlib import Path

from boardgames.agents import (
    Agent,
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
)
from boardgames.arena.runner import play_match
from boardgames.core import AnyGame, GameConfig, JsonValue
from boardgames.games.k_in_a_row import TIC_TAC_TOE, KInARow
from boardgames.logs.schema import LogRecord, MatchFinished
from boardgames.logs.sink import JsonlFile
from tests.arena.support import FakeClock, MemorySink, random_agents


class CostlyAgent:
    """Random play that reports a model-like trace on every decision."""

    def __init__(self, inner: Agent, agent_name: str, cost: float | None) -> None:
        self._inner = inner
        self._name = agent_name
        self._cost = cost
        return

    @property
    def name(self) -> str:
        return self._name

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "llm", "model": {"model": self._name}}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        choice = await self._inner.decide(request)
        assert isinstance(choice, Chosen)
        trace = DecisionTrace(
            reasoning=f"I pick {request.action_text.format_action(choice.action)}",
            memory="notes",
            attempts=({"rejection": {"kind": "illegal", "feedback": "taken"}},),
            illegal_attempts=1,
            api_retries=2,
            prompt_tokens=100,
            completion_tokens=10,
            cost_usd=self._cost,
        )
        return Chosen(choice.action, trace)


def costly_agents(count: int, cost: float | None = 0.001) -> list[Agent]:
    return [
        CostlyAgent(agent, f"model-{seat}", cost)
        for seat, agent in enumerate(random_agents(count))
    ]


def play_records(
    game: AnyGame, config: GameConfig, agents: Sequence[Agent], seed: int, match_id: str
) -> list[LogRecord]:
    sink = MemorySink()
    asyncio.run(
        play_match(
            game, config, seed, agents, match_id=match_id, sink=sink, clock=FakeClock()
        )
    )
    return sink.records


def write_records(path: Path, records: Sequence[LogRecord]) -> None:
    with JsonlFile(path) as sink:
        for record in records:
            sink.write(record)
    return


def write_match(
    directory: Path,
    match_id: str,
    seed: int = 3,
    agents: Sequence[Agent] | None = None,
    game: AnyGame | None = None,
    config: GameConfig | None = None,
) -> list[LogRecord]:
    """Play one tic-tac-toe match (by default) and write its log to `directory`."""
    game = game or KInARow()
    config = config or TIC_TAC_TOE
    records = play_records(
        game, config, agents or random_agents(config.num_players), seed, match_id
    )
    write_records(directory / f"{match_id}.jsonl", records)
    return records


def without_finish(records: Sequence[LogRecord]) -> list[LogRecord]:
    """The log of a match that is still running."""
    return [r for r in records if not isinstance(r, MatchFinished)]
