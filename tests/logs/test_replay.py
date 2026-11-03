import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from boardgames.agents import Agent
from boardgames.arena import cli
from boardgames.arena.runner import play_match
from boardgames.core import AnyGame, GameConfig
from boardgames.games.k_in_a_row import TIC_TAC_TOE, KInARow
from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.logs.replay import (
    LogFormatError,
    ReplayMismatchError,
    read_log,
    replay_match,
)
from boardgames.logs.schema import (
    DecisionRecord,
    EventRecord,
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

AUCTION = SealedAuctionConfig(num_players=3, lots=4)


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
        (KInARow(), TIC_TAC_TOE, 2),
        (SealedAuction(), AUCTION, 3),
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
    records = record_match(KInARow(), TIC_TAC_TOE, agents)
    tampered = replace_first(records, DecisionRecord, {"action": "c3"})
    with pytest.raises(ReplayMismatchError, match="step 1: machine form of 'c3'"):
        replay_match(tampered)
    return


def test_changed_event_text_is_detected() -> None:
    records = record_match(SealedAuction(), AUCTION, random_agents(3))
    tampered = replace_first(records, EventRecord, {"text": "edited"}, skip=4)
    with pytest.raises(ReplayMismatchError, match="step 0, event 4"):
        replay_match(tampered)
    return


def test_changed_seed_is_detected() -> None:
    records = record_match(SealedAuction(), AUCTION, random_agents(3))
    with pytest.raises(ReplayMismatchError, match="step 0"):
        replay_match(replace_first(records, MatchStarted, {"seed": 4}))
    return


def test_changed_observation_is_detected() -> None:
    records = record_match(SealedAuction(), AUCTION, random_agents(3))
    tampered = replace_first(
        records, DecisionRecord, {"observation_digest": "0" * 64}, skip=2
    )
    with pytest.raises(ReplayMismatchError, match="P3 observation differs"):
        replay_match(tampered)
    return


def test_forfeited_match_replays() -> None:
    records = record_match(
        KInARow(), TIC_TAC_TOE, [ScriptedAgent(["b2", "a1"]), ForfeitingAgent()]
    )
    assert replay_match(records).steps == 1
    return


def test_log_without_finish_is_malformed() -> None:
    records = record_match(KInARow(), TIC_TAC_TOE, random_agents(2))
    with pytest.raises(LogFormatError, match="no MatchFinished"):
        replay_match(records[:-1])
    return


def test_read_log_round_trips_a_file(tmp_path: Path) -> None:
    path = tmp_path / "match.jsonl"
    records = record_match(SealedAuction(), AUCTION, random_agents(3))
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
    log = tmp_path / "match.jsonl"
    cli.run_command(cli.parse_arguments(["play", "sealed_auction", "--log", str(log)]))
    cli.run_command(cli.parse_arguments(["replay", str(log)]))
    assert "Replay matches the log: sealed_auction, 18 steps" in capsys.readouterr().out
    return
