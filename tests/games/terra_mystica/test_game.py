"""Tests for the TerraMystica facade: registration, action JSON and full matches."""

import asyncio

from boardgames.arena.runner import play_match
from boardgames.core import create_game, seats
from boardgames.games.terra_mystica import (
    BuildDwelling,
    Hex,
    Pass,
    TerraMystica,
    TerraMysticaConfig,
    TerraMysticaState,
)
from boardgames.games.terra_mystica.constants import MAX_BUILDINGS, BuildingType
from boardgames.logs.replay import replay_match
from tests.arena.support import FakeClock, MemorySink, random_agents
from tests.games.terra_mystica.support import GAME
from tests.invariants.playthrough import random_playthrough


def test_action_json_has_a_type_tag() -> None:
    action = BuildDwelling(Hex(0, 0))
    assert GAME.action_json(action)["type"] == "build_dwelling"
    assert GAME.action_json(Pass()) == {"type": "pass"}


def test_registered_under_its_id() -> None:
    assert isinstance(create_game("terra_mystica"), TerraMystica)


def test_play_match_and_replay() -> None:
    config = TerraMysticaConfig(num_players=2, rounds=1)
    sink = MemorySink()
    asyncio.run(
        play_match(
            GAME,
            config,
            9,
            random_agents(2, 9),
            match_id="terra-mystica-test",
            sink=sink,
            clock=FakeClock(),
        )
    )
    report = replay_match(sink.records)
    assert report.game_id == "terra_mystica"
    assert report.steps >= 1


def check_terra_mystica_state(state: TerraMysticaState) -> None:
    for player in state.players:
        resources = player.resources
        assert resources.coins >= 0
        assert resources.workers >= 0
        assert resources.priests >= 0
        assert resources.power <= 12
        assert 0 <= min(player.cults) <= max(player.cults) <= 10
        assert player.keys >= 0
    for seat in seats(len(state.players)):
        for building in BuildingType:
            assert state.board.count(seat, building) <= MAX_BUILDINGS[building]


def test_random_play_keeps_state_invariants() -> None:
    random_playthrough(
        GAME,
        TerraMysticaConfig(num_players=2, rounds=1),
        13,
        check_terra_mystica_state,
    )


def test_five_player_random_play_keeps_state_invariants() -> None:
    random_playthrough(
        GAME,
        TerraMysticaConfig(num_players=5, rounds=1),
        21,
        check_terra_mystica_state,
    )
