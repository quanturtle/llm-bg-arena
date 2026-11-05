"""Tests for the Terra Mystica config check, opening state and starting dwellings."""

import pytest

from boardgames.core import ConfigError, IllegalActionError, seats
from boardgames.games.terra_mystica import BuildDwelling, TerraMysticaConfig
from boardgames.games.terra_mystica.constants import (
    FACTION_BY_TYPE,
    BuildingType,
    FactionType,
    ScoringAction,
)
from boardgames.games.terra_mystica.model import PlayerState
from boardgames.games.terra_mystica.setup import initial_setup_queue
from tests.games.terra_mystica.support import GAME, P1, P2, P3, notations, play, start


def test_config_validation() -> None:
    assert GAME.parse_config({}) == TerraMysticaConfig()
    for raw in ({"num_players": 1}, {"num_players": 6}, {"rounds": 0}, {"rounds": 7}):
        with pytest.raises(ConfigError):
            GAME.parse_config(raw)


def test_setup_assigns_distinct_factions_and_valid_starting_state() -> None:
    state = start(num_players=5, seed=7, rounds=2)
    factions = [player.faction for player in state.players]
    assert len(set(factions)) == 5
    assert len({player.home_terrain for player in state.players}) == 5
    for player in state.players:
        profile = FACTION_BY_TYPE[player.faction]
        assert player.victory_points == 20
        assert player.resources == profile.starting_resources
        assert player.resources.power == 12
        assert player.cults == profile.starting_cults
        assert len(player.cults) == 4
        assert player.shipping == profile.shipping_start
        assert player.digging == profile.digging_start


def test_setup_asks_each_player_to_place_starting_dwellings() -> None:
    state = start(num_players=4, seed=3)
    expected = sum(player.profile.starting_dwellings for player in state.players)
    placements = 0
    while state.phase == "setup":
        assert GAME.pending_decisions(state)
        state = play(state, notations(state)[0])
        placements += 1
    assert placements == expected
    for seat in seats(4):
        assert state.board.count(seat, BuildingType.DWELLING) == (
            state.players[seat].profile.starting_dwellings
        )
    assert state.setup_queue == ()


def test_setup_queue_handles_nomads_and_chaos_magicians() -> None:
    players = (
        PlayerState(
            faction=FactionType.NOMADS,
            resources=FACTION_BY_TYPE[FactionType.NOMADS].starting_resources,
        ),
        PlayerState(
            faction=FactionType.CHAOS_MAGICIANS,
            resources=FACTION_BY_TYPE[FactionType.CHAOS_MAGICIANS].starting_resources,
        ),
        PlayerState(
            faction=FactionType.WITCHES,
            resources=FACTION_BY_TYPE[FactionType.WITCHES].starting_resources,
        ),
    )
    queue = initial_setup_queue((P1, P2, P3), players)
    assert queue.count(P1) == 3
    assert queue.count(P2) == 1
    assert queue.count(P3) == 2
    assert queue[-1] == P2
    assert queue == (P1, P3, P3, P1, P1, P2)


def test_starting_dwellings_must_be_on_home_terrain() -> None:
    state = start(num_players=2, seed=1)
    player = state.active_player
    home = state.players[player].home_terrain
    wrong = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is not home
    )
    with pytest.raises(IllegalActionError, match="home terrain"):
        GAME.apply(state, player, BuildDwelling(wrong))


def test_spade_round_tile_never_lands_in_rounds_five_or_six() -> None:
    missing = 0
    for seed in range(200):
        state = start(num_players=2, seed=seed, rounds=6)
        positions = [
            index
            for index, tile in enumerate(state.scoring)
            if tile.action is ScoringAction.SPADE
        ]
        assert len(positions) <= 1
        if positions:
            assert positions[0] < 4
        else:
            missing += 1
    assert missing > 0
