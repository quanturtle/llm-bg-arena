import asyncio
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from boardgames.agents import (
    Agent,
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
)
from boardgames.arena.control import PauseGate
from boardgames.arena.runner import (
    DEFAULT_LIMITS,
    AgentContractError,
    MatchContext,
    MatchLimits,
    MatchResult,
    StepLimitError,
    decide_together,
    play_match,
)
from boardgames.core import (
    AnyGame,
    ConfigError,
    Decision,
    GameConfig,
    JsonValue,
    PlayerId,
)
from boardgames.games.catan import Catan, CatanConfig
from boardgames.games.tic_tac_toe import TicTacToe, TicTacToeConfig
from boardgames.llm.model import ModelUnavailableError
from boardgames.logs.replay import replay_match
from boardgames.logs.schema import (
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    MatchFinished,
    MatchStarted,
    MatchStopped,
)
from boardgames.logs.sink import JsonlFile, LogFileError, RecordSink
from tests.arena.support import (
    FakeClock,
    FixedAgent,
    ForfeitingAgent,
    MemorySink,
    RecordingAgent,
    ScriptedAgent,
    random_agents,
)
from tests.llm.requests import tic_tac_toe_request

P1, P2 = PlayerId(0), PlayerId(1)


def run(
    game: AnyGame,
    config: GameConfig,
    agents: Sequence[Agent],
    sink: RecordSink | None = None,
    limits: MatchLimits = DEFAULT_LIMITS,
) -> MatchResult:
    return asyncio.run(
        play_match(
            game,
            config,
            7,
            agents,
            match_id="test",
            sink=sink or MemorySink(),
            clock=FakeClock(),
            limits=limits,
        )
    )


def test_random_match_logs_start_steps_and_finish() -> None:
    sink = MemorySink()
    result = run(TicTacToe(), TicTacToeConfig(), random_agents(2), sink)
    records = sink.records
    decisions = [r for r in records if isinstance(r, DecisionRecord)]
    assert isinstance(records[0], MatchStarted)
    assert isinstance(records[-1], MatchFinished)
    assert [d.step for d in decisions] == list(range(1, result.steps + 1))
    assert [d.player for d in decisions[:4]] == [0, 1, 0, 1]
    assert records[-1].steps == result.steps
    return


def test_scripted_win_ranks_the_winner_first() -> None:
    agents = [ScriptedAgent(["a1", "b1", "c1"]), ScriptedAgent(["a2", "b2"])]
    result = run(TicTacToe(), TicTacToeConfig(), agents)
    assert result.steps == 5
    assert result.ranks == {P1: 1, P2: 2}
    assert result.forfeited == ()
    return


def test_recent_events_start_after_the_players_previous_decision() -> None:
    agents = [RecordingAgent(seed) for seed in range(2)]
    run(TicTacToe(), TicTacToeConfig(), agents)
    first, second = agents[0].requests[0], agents[0].requests[1]
    assert [e.kind for e in first.recent_events] == ["started"]
    assert [e.kind for e in second.recent_events] == ["marked", "marked"]
    return


def test_forfeit_ends_the_match_and_ranks_the_forfeiter_last() -> None:
    sink = MemorySink()
    result = run(
        TicTacToe(), TicTacToeConfig(), [ScriptedAgent(["b2"]), ForfeitingAgent()], sink
    )
    assert result.forfeited == (P2,)
    assert result.ranks == {P1: 1, P2: 2}
    forfeit = next(r for r in sink.records if isinstance(r, ForfeitRecord))
    assert (forfeit.player, forfeit.reason, forfeit.step) == (1, "gave up", 1)
    assert forfeit.trace.illegal_attempts == 3
    return


def test_illegal_choice_is_an_agent_contract_error() -> None:
    agents: list[Agent] = [ScriptedAgent(["b2"]), FixedAgent("b2")]
    with pytest.raises(AgentContractError, match="illegal 'b2'"):
        run(TicTacToe(), TicTacToeConfig(), agents)
    return


def test_step_limit_stops_a_long_match() -> None:
    with pytest.raises(StepLimitError):
        run(
            TicTacToe(),
            TicTacToeConfig(),
            random_agents(2),
            limits=MatchLimits(max_steps=3),
        )
    return


def test_seat_count_must_match_agent_count() -> None:
    with pytest.raises(ConfigError, match="2 seats but 3 agents"):
        run(TicTacToe(), TicTacToeConfig(), random_agents(3))
    return


def test_private_events_keep_their_audience_in_the_log() -> None:
    sink = MemorySink()
    run(Catan(), CatanConfig(num_players=3, victory_points=3), random_agents(3), sink)
    theft = [
        r.audience
        for r in sink.records
        if isinstance(r, EventRecord) and r.kind in ("stole_card", "card_stolen")
    ]
    assert theft[:2] == [[1], [2]]
    return


def test_jsonl_file_writes_one_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "match.jsonl"
    with JsonlFile(path) as log_file:
        run(TicTacToe(), TicTacToeConfig(), random_agents(2), log_file)
    lines = path.read_text().splitlines()
    assert json.loads(lines[0])["type"] == "match_started"
    assert json.loads(lines[-1])["type"] == "match_finished"
    with pytest.raises(LogFileError, match="already exists"):
        JsonlFile(path)
    return


class UnavailableAgent:
    """A model seat whose model never answers."""

    @property
    def name(self) -> str:
        return "down"

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "llm"}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        raise ModelUnavailableError("down failed 6 times")


class SlowAgent:
    """A decision that takes long enough for a sibling's failure to cancel it."""

    def __init__(self) -> None:
        self.finished = 0
        return

    @property
    def name(self) -> str:
        return "slow"

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "llm"}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        await asyncio.sleep(0.2)
        self.finished += 1
        return Chosen(request.action_text.parse_action("a1"), DecisionTrace())


def test_one_failing_simultaneous_decision_cancels_the_other() -> None:
    slow = SlowAgent()
    base = tic_tac_toe_request([])
    requests = [
        base,
        replace(
            base,
            decision=Decision(PlayerId(1), base.decision.kind, base.decision.prompt),
        ),
    ]
    decisions = [request.decision for request in requests]
    context = MatchContext(
        TicTacToe(),
        (slow, UnavailableAgent()),
        MemorySink(),
        FakeClock(),
        "",
        DEFAULT_LIMITS,
    )

    async def fail_together() -> None:
        with pytest.raises(ModelUnavailableError, match="down failed"):
            await decide_together(context, decisions, requests)
        assert slow.finished == 0
        await asyncio.sleep(0.3)
        assert slow.finished == 0
        return

    asyncio.run(fail_together())
    return


def test_a_failed_match_logs_its_stop_and_raises() -> None:
    sink = MemorySink()
    agents = [*random_agents(1), UnavailableAgent()]
    with pytest.raises(ModelUnavailableError):
        run(TicTacToe(), TicTacToeConfig(), agents, sink)
    assert sink.records[-1] == MatchStopped(steps=1, stopped_at=FakeClock().now_iso())
    return


def test_a_paused_match_waits_and_a_cancelled_one_logs_its_stop() -> None:
    sink = MemorySink()
    gate = PauseGate()
    gate.pause()

    async def pause_then_cancel() -> None:
        match = play_match(
            TicTacToe(),
            TicTacToeConfig(),
            7,
            random_agents(2),
            match_id="test",
            sink=sink,
            clock=FakeClock(),
            control=gate,
        )
        task = asyncio.ensure_future(match)
        await asyncio.sleep(0.01)
        assert not any(isinstance(r, DecisionRecord) for r in sink.records)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return

    asyncio.run(pause_then_cancel())
    assert sink.records[-1] == MatchStopped(steps=0, stopped_at=FakeClock().now_iso())
    assert replay_match(sink.records).ending == "stopped"
    return
