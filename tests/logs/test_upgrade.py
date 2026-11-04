from pathlib import Path

import pytest

from boardgames.arena import cli
from boardgames.games.tic_tac_toe import TicTacToe, TicTacToeConfig
from boardgames.logs.replay import read_log, replay_match
from boardgames.logs.schema import DecisionRecord, EventRecord, LogRecord, MatchStarted
from boardgames.logs.upgrade import LogUpgradeError, upgrade_records
from tests.arena.support import ScriptedAgent
from tests.llm.fakes import FirstListedMove
from tests.web.support import play_records


def scripted_records() -> list[LogRecord]:
    agents = [ScriptedAgent(["a1", "b1", "c1"]), ScriptedAgent(["a2", "b2"])]
    return play_records(TicTacToe(), TicTacToeConfig(), agents, 3, "m")


def event_texts(records: list[LogRecord]) -> list[str]:
    return [record.text for record in records if isinstance(record, EventRecord)]


def test_an_older_log_is_re_recorded_under_the_current_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = scripted_records()
    older = [
        r.model_copy(update={"text": "Old wording."})
        if isinstance(r, EventRecord)
        else r
        for r in records
    ]
    monkeypatch.setattr(TicTacToe, "rules_version", 2)
    upgraded = upgrade_records(older)
    start = upgraded[0]
    assert isinstance(start, MatchStarted)
    assert start.rules_version == 2
    assert event_texts(upgraded) == event_texts(records)
    return


def test_a_move_the_current_rules_reject_stops_the_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older = [
        r.model_copy(update={"action": "a1"})
        if isinstance(r, DecisionRecord) and r.step == 2
        else r
        for r in scripted_records()
    ]
    monkeypatch.setattr(TicTacToe, "rules_version", 2)
    with pytest.raises(LogUpgradeError, match="step 2: the current rules reject 'a1'"):
        upgrade_records(older)
    return


def test_cli_upgrade_log_rewrites_an_older_log_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    offline = cli.AppConfig(api_key=None, model=FirstListedMove())
    log = tmp_path / "match.jsonl"
    config = tmp_path / "match.yaml"
    config.write_text("game: tic_tac_toe\n", encoding="utf-8")
    cli.run_command(
        cli.parse_arguments(["play", str(config), "--log", str(log)]), offline
    )
    monkeypatch.setattr(TicTacToe, "rules_version", 2)
    upgrade = cli.parse_arguments(["upgrade-log", str(log)])
    cli.run_command(upgrade, offline)
    cli.run_command(upgrade, offline)
    output = capsys.readouterr().out
    assert "upgraded from tic_tac_toe rules v1 to v2" in output
    assert "already on tic_tac_toe rules v2" in output
    replay_match(read_log(log))
    return
