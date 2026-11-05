"""Tests for the Puerto Rico opening table and config checks."""

import pytest

from boardgames.core import ConfigError, create_game
from boardgames.games.puerto_rico import PuertoRico, PuertoRicoConfig
from boardgames.games.puerto_rico.constants import (
    COLONIST_SUPPLY,
    GOOD_SUPPLY,
    PLANTATION_TILES,
    ROLES_BY_PLAYERS,
    SHIP_CAPACITIES,
    STARTING_DOUBLOONS,
)
from tests.games.puerto_rico.support import GAME, start


def test_initial_state_has_governor_and_role_selection() -> None:
    state = start(seed=7)
    assert state.phase == "role_selection"
    assert state.active_role is None
    assert state.order[0] == state.governor
    assert state.active_player == state.governor


def test_setup_for_three_players() -> None:
    state = start(num_players=3, seed=7)
    assert len(state.players) == 3
    assert all(player.doubloons == STARTING_DOUBLOONS[3] for player in state.players)
    assert len(state.roles) == 6 == len(ROLES_BY_PLAYERS[3])
    assert "prospector" not in {role.role for role in state.roles}
    assert len(state.face_up) == 4
    assert len(state.plantation_deck) == (sum(PLANTATION_TILES.values()) - 3 - 4)
    assert state.colonist_ship == 3
    assert state.colonist_supply == COLONIST_SUPPLY[3]
    assert state.vp_supply == 75
    assert state.trading_house == ()
    assert state.quarry_supply == 8
    assert state.goods_supply == GOOD_SUPPLY
    assert tuple(ship.capacity for ship in state.cargo_ships) == SHIP_CAPACITIES[3]
    indigo_count = 2
    for order_index, seat in enumerate(state.order):
        plantation = state.players[seat].plantations[0]
        assert plantation.good == ("indigo" if order_index < indigo_count else "corn")
        assert not plantation.colonized


@pytest.mark.parametrize(
    ("num_players", "role_count", "indigo_count"),
    [(4, 7, 2), (5, 8, 3)],
)
def test_setup_for_four_and_five_players(
    num_players: int, role_count: int, indigo_count: int
) -> None:
    state = start(num_players=num_players, seed=11)
    assert len(state.roles) == role_count == len(ROLES_BY_PLAYERS[num_players])
    role_names = {role.role for role in state.roles}
    assert "prospector" in role_names
    assert ("prospector_2" in role_names) is (num_players == 5)
    assert all(
        player.doubloons == STARTING_DOUBLOONS[num_players] for player in state.players
    )
    assert state.colonist_supply == COLONIST_SUPPLY[num_players]
    assert state.vp_supply == {4: 100, 5: 122}[num_players]
    assert len(state.face_up) == num_players + 1
    for order_index, seat in enumerate(state.order):
        good = state.players[seat].plantations[0].good
        assert good == ("indigo" if order_index < indigo_count else "corn")


def test_setup_is_deterministic_per_seed() -> None:
    assert start(seed=9) == start(seed=9)
    assert GAME.setup(PuertoRicoConfig(num_players=3), 9).events == (
        GAME.setup(PuertoRicoConfig(num_players=3), 9).events
    )
    assert start(seed=9) != start(seed=10)


def test_config_validation_and_registry() -> None:
    assert GAME.parse_config({}) == PuertoRicoConfig()
    config = PuertoRicoConfig(num_players=5, victory_point_supply=50, max_rounds=10)
    assert GAME.parse_config(GAME.config_json(config)) == config
    for raw in (
        {"num_players": 2},
        {"num_players": 6},
        {"victory_point_supply": -1},
        {"max_rounds": -1},
    ):
        with pytest.raises(ConfigError):
            GAME.parse_config(raw)
    assert isinstance(create_game("puerto_rico"), PuertoRico)
