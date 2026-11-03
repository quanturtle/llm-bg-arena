from pathlib import Path

import pytest
import yaml

from boardgames.arena.match_config import (
    DEFAULT_MODEL,
    LlmSeat,
    MatchConfig,
    llm_agent_settings,
    load_match_config,
    parse_match_config,
    seats_for,
)
from boardgames.core import ConfigError
from boardgames.llm.model import ModelSettings

FULL = """
game: puerto_rico
config: {num_players: 3}
seed: 7
log: runs/puerto_rico.jsonl
cache: true
seats:
  - model: anthropic/claude-haiku-5.5
    reasoning_effort: high
    temperature: 0.7
    max_tokens: 512
    output_mode: tools
    max_tool_calls: 8
    label: haiku
    fallback: forfeit
  - model: openai/gpt-5-mini
    extra: {provider: {order: [openai]}}
    extractor: openai/gpt-5-nano
  - {}
"""


def full_config() -> MatchConfig:
    return parse_match_config(yaml.safe_load(FULL), "test")


def llm_seat(config: MatchConfig, index: int) -> LlmSeat:
    assert config.seats is not None
    return config.seats[index]


def test_full_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "match.yaml"
    path.write_text(FULL, encoding="utf-8")
    config = load_match_config(path)
    assert (config.game, config.seed) == ("puerto_rico", 7)
    assert config.config == {"num_players": 3}
    assert config.log == Path("runs/puerto_rico.jsonl")
    assert config.cache is True
    assert config.seats is not None
    assert llm_agent_settings(config.seats[2], 0).model.model == DEFAULT_MODEL
    return


def test_each_seat_has_its_own_settings_and_defaults_fill_the_rest() -> None:
    config = full_config()
    settings = llm_agent_settings(llm_seat(config, 0), seed=3)
    assert settings.model.model == "anthropic/claude-haiku-5.5"
    assert (settings.model.temperature, settings.model.max_tokens) == (0.7, 512)
    assert (settings.model.reasoning_effort, settings.model.seed) == ("high", 3)
    assert (settings.label, settings.fallback) == ("haiku", "forfeit")
    assert (settings.prompt.output_mode, settings.max_tool_calls) == ("tools", 8)
    settings = llm_agent_settings(llm_seat(config, 1), seed=4)
    assert settings.model.temperature is None
    assert settings.model.max_tokens == ModelSettings(model="m").max_tokens
    assert settings.model.extra == {"provider": {"order": ["openai"]}}
    return


def test_a_shared_llm_section_and_random_seats_are_rejected() -> None:
    with pytest.raises(ConfigError, match=r"llm: Extra inputs"):
        parse_match_config({"game": "x", "llm": {"temperature": 0.2}}, "test")
    with pytest.raises(ConfigError, match=r"seats\.0\.agent: Extra inputs"):
        parse_match_config({"game": "x", "seats": [{"agent": "random"}]}, "test")
    return


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.5),
        ("top_p", 1.5),
        ("max_tokens", 0),
        ("timeout_seconds", 0),
        ("max_tool_calls", 0),
        ("max_illegal_retries", -1),
        ("thinking_budget_tokens", 0),
    ],
)
def test_out_of_range_setting_is_a_config_error(key: str, value: float) -> None:
    raw = {"game": "x", "seats": [{key: value}]}
    with pytest.raises(ConfigError, match=rf"seats\.0\.{key}: Input should be"):
        parse_match_config(raw, "test")
    return


def test_unknown_key_is_a_config_error() -> None:
    raw = {"game": "x", "seats": [{"model": "m", "temprature": 1}]}
    with pytest.raises(ConfigError, match=r"seats\.0\.temprature"):
        parse_match_config(raw, "test")
    return


def test_file_that_is_not_a_mapping_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "match.yaml"
    path.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_match_config(path)
    return


def test_seats_default_to_the_default_model_and_counts_must_match() -> None:
    seats = seats_for(MatchConfig(game="tic_tac_toe"), 2)
    assert seats == [LlmSeat(), LlmSeat()]
    assert llm_agent_settings(LlmSeat(), 1).model.model == DEFAULT_MODEL
    bare = parse_match_config({"game": "x", "seats": [{}, {"model": "a/b"}]}, "t")
    assert [seat.model for seat in bare.seats or []] == [None, "a/b"]
    with pytest.raises(ConfigError, match="seats 2 players but the file lists 3"):
        seats_for(full_config(), 2)
    return
