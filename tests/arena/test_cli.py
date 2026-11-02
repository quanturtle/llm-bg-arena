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
    assert "unknown agent spec 'alien'; known: random, llm:<model>" in (
        capsys.readouterr().err
    )
    return


def test_llm_spec_builds_an_llm_agent_with_command_line_settings() -> None:
    args = cli.parse_arguments(
        [
            "play",
            "k_in_a_row",
            "--temperature",
            "0.3",
            "--max-retries",
            "1",
            "--fallback",
            "forfeit",
        ]
    )
    options = cli.llm_options(args)
    agent = cli.build_agent(
        "llm:anthropic/claude-haiku-5-5", 7, 1, options, cli.chat_model(options)
    )
    settings = agent.settings()
    assert agent.name == "anthropic/claude-haiku-5-5"
    assert settings["kind"] == "llm"
    assert (settings["max_illegal_retries"], settings["fallback"]) == (1, "forfeit")
    return


def test_games_lists_registered_ids(capsys: pytest.CaptureFixture[str]) -> None:
    cli.run_command(cli.parse_arguments(["games"]))
    assert capsys.readouterr().out.split() == ["k_in_a_row", "sealed_auction"]
    return
