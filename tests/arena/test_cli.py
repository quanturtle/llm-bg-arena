from pathlib import Path

import pytest

from tabletop_arena.arena import cli


def test_play_prints_the_match_and_writes_a_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "match.jsonl"
    cli.run_command(
        cli.parse_arguments(["play", "k_in_a_row", "--seed", "3", "--log", str(log)])
    )
    output = capsys.readouterr().out
    assert "k_in_a_row (seed 3): P1 random, P2 random" in output
    assert "Ranks:" in output
    assert log.exists()
    return


def test_unknown_agent_spec_exits_with_status_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli.parse_arguments(
        ["play", "k_in_a_row", "--agent", "alien", "--agent", "random"]
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.run_command(args)
    assert exit_info.value.code == 1
    assert "unknown agent spec 'alien'" in capsys.readouterr().err
    return


def test_games_lists_registered_ids(capsys: pytest.CaptureFixture[str]) -> None:
    cli.run_command(cli.parse_arguments(["games"]))
    assert capsys.readouterr().out.split() == ["k_in_a_row", "sealed_auction"]
    return
