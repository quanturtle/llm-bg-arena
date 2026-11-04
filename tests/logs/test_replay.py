import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from boardgames.agents import Agent
from boardgames.arena import cli
from boardgames.arena.runner import play_match
from boardgames.core import AnyGame, GameConfig
from boardgames.games.catan import Catan, CatanConfig
from boardgames.games.tic_tac_toe import TicTacToe, TicTacToeConfig
from boardgames.logs.replay import (
    LogFormatError,
    ReplayMismatchError,
    read_log,
    replay_match,
)
from boardgames.logs.schema import (
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
)
from boardgames.logs.sink import JsonlFile
from tests.arena.support import (
    FakeClock,
    ForfeitingAgent,
    MemorySink,
    ScriptedAgent,
    random_agents,
)
from tests.llm.fakes import FirstListedMove

CATAN = CatanConfig(num_players=3, victory_points=3)


def record_match(
    game: AnyGame, config: GameConfig, agents: Sequence[Agent], seed: int = 3
) -> list[LogRecord]:
    sink = MemorySink()
    asyncio.run(
        play_match(
            game, config, seed, agents, match_id="m", sink=sink, clock=FakeClock()
        )
    )
    return sink.records


def replace_first[R: LogRecord](
    records: list[LogRecord], kind: type[R], update: dict[str, object], skip: int = 0
) -> list[LogRecord]:
    """Copy of `records` with the (skip+1)-th record of `kind` updated."""
    result = list(records)
    matches = [i for i, record in enumerate(records) if isinstance(record, kind)]
    index = matches[skip]
    result[index] = records[index].model_copy(update=update)
    return result


@pytest.mark.parametrize("seed", range(5))
def test_random_matches_replay_exactly(seed: int) -> None:
    cases: list[tuple[AnyGame, GameConfig, int]] = [
        (TicTacToe(), TicTacToeConfig(), 2),
        (Catan(), CATAN, 3),
    ]
    for game, config, players in cases:
        records = record_match(game, config, random_agents(players, seed), seed)
        report = replay_match(records)
        finish = records[-1]
        assert isinstance(finish, MatchFinished)
        assert report.steps == finish.steps
    return


def test_changed_action_is_detected() -> None:
    agents = [ScriptedAgent(["a1", "b1", "c1"]), ScriptedAgent(["a2", "b2"])]
    records = record_match(TicTacToe(), TicTacToeConfig(), agents)
    tampered = replace_first(records, DecisionRecord, {"action": "c3"})
    with pytest.raises(ReplayMismatchError, match="step 1: machine form of 'c3'"):
        replay_match(tampered)
    return


def test_changed_event_text_is_detected() -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    tampered = replace_first(records, EventRecord, {"text": "edited"}, skip=2)
    with pytest.raises(ReplayMismatchError, match="step 0, event 2"):
        replay_match(tampered)
    return


def test_changed_seed_is_detected() -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    with pytest.raises(ReplayMismatchError, match="step 0"):
        replay_match(replace_first(records, MatchStarted, {"seed": 4}))
    return


def test_changed_observation_is_detected() -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    tampered = replace_first(
        records, DecisionRecord, {"observation_digest": "0" * 64}, skip=2
    )
    with pytest.raises(ReplayMismatchError, match="P2 observation differs"):
        replay_match(tampered)
    return


def test_changed_observation_data_is_detected() -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    first = next(record for record in records if isinstance(record, DecisionRecord))
    observation = dict(first.observation, hand_sizes=[99, 99, 99])
    tampered = replace_first(records, DecisionRecord, {"observation": observation})
    with pytest.raises(ReplayMismatchError, match="P1 logged observation data"):
        replay_match(tampered)
    return


def test_event_at_a_step_without_a_decision_is_detected() -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    orphan = EventRecord(step=40, kind="won", text="P1 wins", data={}, audience=[0])
    tampered = [*records[:-1], orphan, records[-1]]
    with pytest.raises(ReplayMismatchError, match="events at step 40 follow no"):
        replay_match(tampered)
    return


def test_observed_step_the_replay_has_not_reached_is_detected() -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    tampered = replace_first(records, DecisionRecord, {"observed_at_step": 99})
    with pytest.raises(ReplayMismatchError, match="observed_at_step 99 is not"):
        replay_match(tampered)
    return


@pytest.mark.parametrize("update", [{"kind": "move"}, {"prompt": "Pick one."}])
def test_changed_decision_kind_or_prompt_is_detected(
    update: dict[str, object],
) -> None:
    records = record_match(Catan(), CATAN, random_agents(3))
    with pytest.raises(ReplayMismatchError, match="step 1: P1 decision: log has"):
        replay_match(replace_first(records, DecisionRecord, update))
    return


def test_changed_forfeit_step_is_detected() -> None:
    records = record_match(
        TicTacToe(), TicTacToeConfig(), [ScriptedAgent(["b2", "a1"]), ForfeitingAgent()]
    )
    tampered = replace_first(records, ForfeitRecord, {"step": 5})
    with pytest.raises(ReplayMismatchError, match="forfeit at step 5 follows step 1"):
        replay_match(tampered)
    return


def test_forfeited_match_replays() -> None:
    records = record_match(
        TicTacToe(), TicTacToeConfig(), [ScriptedAgent(["b2", "a1"]), ForfeitingAgent()]
    )
    assert replay_match(records).steps == 1
    return


def test_log_without_finish_is_malformed() -> None:
    records = record_match(TicTacToe(), TicTacToeConfig(), random_agents(2))
    with pytest.raises(LogFormatError, match="no MatchFinished"):
        replay_match(records[:-1])
    return


def test_read_log_round_trips_a_file(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    records = record_match(Catan(), CATAN, random_agents(3))
    with JsonlFile(path) as log_file:
        for record in records:
            log_file.write(record)
    assert read_log(path) == records
    return


def test_read_log_rejects_a_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"type": "event", "step": "x"}\n')
    with pytest.raises(LogFormatError, match=r"bad\.jsonl:1"):
        read_log(path)
    return


def test_cli_replay_reports_a_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    offline = cli.AppConfig(api_key=None, model=FirstListedMove())
    log = tmp_path / "match.jsonl"
    config = tmp_path / "match.yaml"
    config.write_text("game: tic_tac_toe\n", encoding="utf-8")
    play = cli.parse_arguments(["play", str(config), "--log", str(log)])
    cli.run_command(play, offline)
    cli.run_command(cli.parse_arguments(["replay", str(log)]), offline)
    assert "Replay matches the log: tic_tac_toe, 7 steps" in capsys.readouterr().out
    return
