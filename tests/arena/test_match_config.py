from pathlib import Path

import pytest
import yaml

from boardgames.arena.match_config import (
    LlmSeat,
    MatchConfig,
    RandomSeat,
    llm_agent_settings,
    load_match_config,
    merged_options,
    parse_match_config,
    seats_for,
)
from boardgames.core import ConfigError

FULL = """
game: sealed_auction
config: {num_players: 3}
seed: 7
log: runs/auction.jsonl
llm:
  temperature: 0.2
  max_tokens: 512
  output_mode: tools
  max_tool_calls: 8
  cache: true
  extractor: openai/gpt-5-mini
seats:
  - agent: llm
    model: anthropic/claude-haiku-5-5
    reasoning_effort: high
    temperature: 0.7
    label: haiku
    fallback: forfeit
  - agent: llm
    model: openai/gpt-5-mini
    extra: {provider: {order: [openai]}}
  - agent: random
"""


def full_config() -> MatchConfig:
    return parse_match_config(yaml.safe_load(FULL), "test")


def llm_seat(config: MatchConfig, index: int) -> LlmSeat:
    assert config.seats is not None
    seat = config.seats[index]
    assert isinstance(seat, LlmSeat)
    return seat


def test_full_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "match.yaml"
    path.write_text(FULL, encoding="utf-8")
    config = load_match_config(path)
    assert (config.game, config.seed) == ("sealed_auction", 7)
    assert config.config == {"num_players": 3}
    assert config.log == Path("runs/auction.jsonl")
    assert config.llm.cache is True
    assert config.seats is not None
    assert [type(seat) for seat in config.seats] == [LlmSeat, LlmSeat, RandomSeat]
    return


def test_seat_values_override_file_defaults() -> None:
    config = full_config()
    first = llm_seat(config, 0)
    settings = llm_agent_settings(first, merged_options(first, config.llm), seed=3)
    assert settings.model.model == "anthropic/claude-haiku-5-5"
    assert (settings.model.temperature, settings.model.max_tokens) == (0.7, 512)
    assert (settings.model.reasoning_effort, settings.model.seed) == ("high", 3)
    assert (settings.label, settings.fallback) == ("haiku", "forfeit")
    assert settings.max_illegal_retries == 3
    assert (settings.prompt.output_mode, settings.max_tool_calls) == ("tools", 8)
    second = llm_seat(config, 1)
    options = merged_options(second, config.llm)
    settings = llm_agent_settings(second, options, seed=4)
    assert settings.model.temperature == 0.2
    assert settings.model.extra == {"provider": {"order": ["openai"]}}
    assert options.extractor == "openai/gpt-5-mini"
    return


def test_seat_null_takes_the_built_in_default_over_the_file_default() -> None:
    raw = {
        "game": "k_in_a_row",
        "llm": {"max_tokens": 512, "reasoning_effort": "high"},
        "seats": [
            {
                "agent": "llm",
                "model": "m",
                "max_tokens": None,
                "reasoning_effort": None,
                "thinking_budget_tokens": 2048,
            }
        ],
    }
    config = parse_match_config(raw, "test")
    seat = llm_seat(config, 0)
    model = llm_agent_settings(seat, merged_options(seat, config.llm), seed=3).model
    assert model.max_tokens == 1024
    assert (model.reasoning_effort, model.thinking_budget_tokens) == (None, 2048)
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
    raw = {"game": "x", "llm": {key: value}}
    with pytest.raises(ConfigError, match=rf"llm\.{key}: Input should be"):
        parse_match_config(raw, "test")
    return


def test_unknown_key_is_a_config_error() -> None:
    raw = {"game": "x", "seats": [{"agent": "llm", "model": "m", "temprature": 1}]}
    with pytest.raises(ConfigError, match=r"seats\.0\.llm\.temprature"):
        parse_match_config(raw, "test")
    return


def test_file_that_is_not_a_mapping_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "match.yaml"
    path.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_match_config(path)
    return


def test_missing_seats_are_random_and_counts_must_match() -> None:
    assert seats_for(MatchConfig(game="k_in_a_row"), 2) == [
        RandomSeat(agent="random"),
        RandomSeat(agent="random"),
    ]
    with pytest.raises(ConfigError, match="seats 2 players but the file lists 3"):
        seats_for(full_config(), 2)
    return
