import asyncio

import pytest

from boardgames.arena.runner import play_match
from boardgames.core import ConfigError, create_game
from boardgames.games.catan import Catan, CatanConfig, CatanState
from boardgames.games.catan.model import hand_total
from boardgames.games.catan.rules import longest_road_lengths
from boardgames.logs.replay import replay_match
from boardgames.logs.schema import LogRecord
from tests.arena.support import FakeClock, MemorySink, random_agents
from tests.games.catan.support import CONFIG, GAME
from tests.invariants.playthrough import random_playthrough


def record_match(config: CatanConfig, seed: int) -> list[LogRecord]:
    sink = MemorySink()
    asyncio.run(
        play_match(
            GAME,
            config,
            seed,
            random_agents(config.num_players, seed),
            match_id="catan-test",
            sink=sink,
            clock=FakeClock(),
        )
    )
    return sink.records


def test_config_validation_and_registry() -> None:
    assert GAME.parse_config({}) == CatanConfig()
    assert GAME.parse_config(GAME.config_json(CONFIG)) == CONFIG
    for raw in (
        {"num_players": 2},
        {"num_players": 5},
        {"victory_points": 2},
        {"max_offers_per_turn": 21},
    ):
        with pytest.raises(ConfigError):
            GAME.parse_config(raw)
    assert isinstance(create_game("catan"), Catan)


def test_same_seed_replays_to_the_same_log() -> None:
    config = CatanConfig(num_players=3, victory_points=4)
    first = record_match(config, 4)
    second = record_match(config, 4)
    assert first == second
    report = replay_match(first)
    assert report.game_id == "catan"
    assert report.steps > 0


def check_playthrough_state(state: CatanState) -> None:
    """Cards never go negative and award holders meet the minimums."""
    assert all(hand_total(hand) >= 0 for hand in state.hands)
    assert all(all(card >= 0 for card in hand) for hand in state.dev_hands)
    if state.longest_road is not None:
        assert longest_road_lengths(state)[state.longest_road] >= 5
    if state.largest_army is not None:
        assert state.knights_played[state.largest_army] >= 3
    if state.phase == "discard":
        assert any(state.discard_remaining)
    return


def test_random_playthroughs_reach_ten_points_and_build_a_city() -> None:
    config = CatanConfig(num_players=3)
    cities = 0
    for seed in (3,):
        state, _ = random_playthrough(GAME, config, seed, check_playthrough_state)
        assert state.winner is not None
        assert GAME.scores(state).points[state.winner] >= config.victory_points == 10
        cities += sum(
            1
            for building in state.buildings
            if building is not None and building.kind == "city"
        )
    assert cities >= 1
