import webbrowser
from pathlib import Path
from types import SimpleNamespace

import pytest

from boardgames.arena import cli
from boardgames.arena.lineup import (
    API_KEY_VARIABLE,
    agent_for_seat,
    derive_seed,
    openrouter_model,
    player_names,
)
from boardgames.arena.match_config import LlmSeat
from tests.llm.fakes import FirstListedMove


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every seat plays the first listed move, without a key or network."""
    monkeypatch.setattr(cli, "chat_model_from_environment", FirstListedMove)
    return


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "match.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def error_lines(argv: list[str], capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Standard error of a command that must exit with status 1."""
    with pytest.raises(SystemExit) as exit_info:
        cli.run_command(cli.parse_arguments(argv))
    assert exit_info.value.code == 1
    return capsys.readouterr().err.splitlines()


def test_existing_log_path_is_one_error_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], offline: None
) -> None:
    log = tmp_path / "match.jsonl"
    log.write_text("kept\n", encoding="utf-8")
    config = write_config(tmp_path, f"game: tic_tac_toe\nlog: {log}\n")
    assert error_lines(["play", str(config)], capsys) == [
        f"error: {log} already exists; logs are never overwritten"
    ]
    assert log.read_text(encoding="utf-8") == "kept\n"
    return


def test_missing_replay_log_is_one_error_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "missing.jsonl"
    assert error_lines(["replay", str(log)], capsys) == [
        f"error: cannot read {log}: No such file or directory"
    ]
    return


def test_config_that_is_not_utf8_is_one_error_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "match.yaml"
    config.write_bytes(b"\x89PNG\x00\xff\xfe")
    (line,) = error_lines(["play", str(config)], capsys)
    assert line.startswith(f"error: {config} is not UTF-8 text:")
    return


def test_play_runs_the_configured_match_and_writes_its_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], offline: None
) -> None:
    log = tmp_path / "match.jsonl"
    config = write_config(tmp_path, f"game: tic_tac_toe\nseed: 3\nlog: {log}\n")
    cli.run_command(cli.parse_arguments(["play", str(config)]))
    output = capsys.readouterr().out
    model = "qwen/qwen3.7-flash"
    assert f"tic_tac_toe (seed 3): P1 {model} #1, P2 {model} #2" in output
    assert "Ranks:" in output
    assert log.exists()
    return


def test_seed_and_log_flags_override_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], offline: None
) -> None:
    config = write_config(tmp_path, "game: tic_tac_toe\nseed: 3\n")
    log = tmp_path / "override.jsonl"
    cli.run_command(
        cli.parse_arguments(["play", str(config), "--seed", "5", "--log", str(log)])
    )
    assert "tic_tac_toe (seed 5)" in capsys.readouterr().out
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


def test_llm_seat_builds_an_llm_agent_with_its_settings() -> None:
    seat = LlmSeat(
        model="anthropic/claude-haiku-5-5",
        fallback="forfeit",
        max_illegal_retries=1,
        extractor="openai/gpt-5-mini",
    )
    agent = agent_for_seat(seat, "haiku #2", 7, 1, openrouter_model("k"))
    settings = agent.settings()
    assert agent.name == "haiku #2"
    assert settings["kind"] == "llm"
    assert (settings["max_illegal_retries"], settings["fallback"]) == (1, "forfeit")
    assert settings["extractor"] == "openai/gpt-5-mini"
    return


def test_repeated_names_get_a_number_and_unique_ones_stay() -> None:
    seats = [LlmSeat(), LlmSeat(model="a/b"), LlmSeat(), LlmSeat(label="me")]
    assert player_names(seats) == [
        "qwen/qwen3.7-flash #1",
        "a/b",
        "qwen/qwen3.7-flash #2",
        "me",
    ]
    return


def test_seat_seed_sets_only_the_model_seed_modulo_2_31() -> None:
    seat = LlmSeat(model="openai/gpt-x", seed=2**31 + 5)
    agent = agent_for_seat(seat, "openai/gpt-x", 7, 1, openrouter_model("k"))
    settings = agent.settings()
    model = settings["model"]
    assert isinstance(model, dict)
    assert model["seed"] == 5
    assert settings["seed"] == derive_seed(7, 1)
    return


def test_reasoning_conflict_is_reported_before_the_key_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(API_KEY_VARIABLE, raising=False)
    config = write_config(
        tmp_path,
        "game: tic_tac_toe\nseats:\n"
        "  - {}\n"
        "  - {model: a/b, reasoning_effort: high, thinking_budget_tokens: 2}\n",
    )
    assert error_lines(["play", str(config)], capsys) == [
        f"error: {config}: seats.1: set reasoning_effort or thinking_budget_tokens, "
        "not both"
    ]
    return


def test_llm_seat_without_a_key_exits_with_status_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(API_KEY_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    config = write_config(
        tmp_path,
        "game: tic_tac_toe\nseats:\n  - {model: openai/gpt-x}\n  - {}\n",
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.run_command(cli.parse_arguments(["play", str(config)]))
    assert exit_info.value.code == 1
    assert "set OPENROUTER_API_KEY" in capsys.readouterr().err
    assert not (tmp_path / cli.DEFAULT_LOG_DIR).exists()
    assert list(tmp_path.rglob("*.jsonl")) == []
    return


def test_browser_waits_for_our_server_not_any_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    other_server = SimpleNamespace(started=False, should_exit=True)
    cli.open_when_started("http://127.0.0.1:8765/match/", other_server, 0.1)
    assert opened == []
    our_server = SimpleNamespace(started=True, should_exit=False)
    cli.open_when_started("http://127.0.0.1:8765/match/", our_server, 0.1)
    assert opened == ["http://127.0.0.1:8765/match/"]
    return


def test_games_lists_registered_ids(capsys: pytest.CaptureFixture[str]) -> None:
    cli.run_command(cli.parse_arguments(["games"]))
    assert capsys.readouterr().out.split() == [
        "catan",
        "puerto_rico",
        "terra_mystica",
        "tic_tac_toe",
    ]
    return
