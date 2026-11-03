from pathlib import Path

import pytest

from boardgames.arena import cli
from boardgames.arena.match_config import LlmDefaults, LlmSeat


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "match.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_play_runs_the_configured_match_and_writes_its_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "match.jsonl"
    config = write_config(tmp_path, f"game: k_in_a_row\nseed: 3\nlog: {log}\n")
    cli.run_command(cli.parse_arguments(["play", str(config)]))
    output = capsys.readouterr().out
    assert "k_in_a_row (seed 3): P1 random, P2 random" in output
    assert "Ranks:" in output
    assert log.exists()
    return


def test_seed_and_log_flags_override_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, "game: k_in_a_row\nseed: 3\n")
    log = tmp_path / "override.jsonl"
    cli.run_command(
        cli.parse_arguments(["play", str(config), "--seed", "5", "--log", str(log)])
    )
    assert "k_in_a_row (seed 5)" in capsys.readouterr().out
    assert log.exists()
    return


def test_unknown_game_exits_with_status_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = write_config(tmp_path, "game: alien\n")
    with pytest.raises(SystemExit) as exit_info:
        cli.run_command(cli.parse_arguments(["play", str(config)]))
    assert exit_info.value.code == 1
    assert "unknown game 'alien'" in capsys.readouterr().err
    return


def test_llm_seat_builds_an_llm_agent_with_merged_settings() -> None:
    seat = LlmSeat(agent="llm", model="anthropic/claude-haiku-5-5", fallback="forfeit")
    defaults = LlmDefaults(max_illegal_retries=1, extractor="openai/gpt-5-mini")
    agent = cli.agent_for_seat(seat, defaults, 7, 1, cli.chat_model(False, "k"))
    settings = agent.settings()
    assert agent.name == "anthropic/claude-haiku-5-5"
    assert settings["kind"] == "llm"
    assert (settings["max_illegal_retries"], settings["fallback"]) == (1, "forfeit")
    assert settings["extractor"] == "openai/gpt-5-mini"
    return


def test_llm_seat_without_a_key_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(cli.API_KEY_VARIABLE, raising=False)
    config = write_config(
        tmp_path,
        "game: k_in_a_row\nseats:\n  - {agent: llm, model: openai/gpt-x}\n"
        "  - {agent: random}\n",
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.run_command(cli.parse_arguments(["play", str(config)]))
    assert exit_info.value.code == 1
    assert "set OPENROUTER_API_KEY" in capsys.readouterr().err
    return


def test_games_lists_registered_ids(capsys: pytest.CaptureFixture[str]) -> None:
    cli.run_command(cli.parse_arguments(["games"]))
    assert capsys.readouterr().out.split() == [
        "catan",
        "k_in_a_row",
        "sealed_auction",
    ]
    return
