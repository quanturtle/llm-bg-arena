"""Tests for the Puerto Rico Craftsman: production, the Factory and the privilege."""

from dataclasses import replace

from boardgames.games.puerto_rico.model import OwnedBuilding, Plantation, goods_get
from boardgames.games.puerto_rico.roles.craftsman import (
    craftsman_actions,
    run_production,
)
from tests.games.puerto_rico.support import (
    GAME,
    drain,
    notations,
    play,
    select_role,
    start,
    with_buildings,
    with_plantations,
)


def test_craftsman_produces_for_everyone_and_gives_a_privilege() -> None:
    state = start(seed=8)
    chooser = state.order[0]
    state = with_plantations(
        state,
        chooser,
        Plantation("corn", True),
        Plantation("indigo", True),
    )
    state = with_buildings(state, chooser, OwnedBuilding("small_indigo_plant", 1))
    state = select_role(state, "craftsman")
    assert state.phase == "craftsman_action"
    assert state.active_player == chooser
    assert goods_get(state.players[chooser].goods, "corn") == 1
    assert goods_get(state.players[chooser].goods, "indigo") == 1
    options = notations(state)
    assert "privilege corn" in options
    state = play(state, "privilege corn")
    assert goods_get(state.players[chooser].goods, "corn") == 2
    state = drain(state)
    assert state.phase == "role_selection"


def test_craftsman_factory_bonus() -> None:
    state = start(seed=8)
    chooser = state.order[0]
    state = with_plantations(
        state,
        chooser,
        Plantation("corn", True),
        Plantation("indigo", True),
        Plantation("sugar", True),
    )
    state = with_buildings(
        state,
        chooser,
        OwnedBuilding("factory", 1),
        OwnedBuilding("small_indigo_plant", 1),
        OwnedBuilding("small_sugar_mill", 1),
    )
    before = state.players[chooser].doubloons
    state = select_role(state, "craftsman")
    assert state.players[chooser].doubloons == before + 2


def test_production_is_limited_by_the_goods_supply() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_plantations(state, player, Plantation("indigo", True))
    state = with_buildings(state, player, OwnedBuilding("small_indigo_plant", 1))
    state = replace(state, goods_supply=(10, 0, 11, 9, 9))
    state, _ = run_production(state, player)
    assert goods_get(state.players[player].goods, "indigo") == 0


def test_craftsman_privilege_needs_a_producible_good_in_the_bank() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_plantations(state, player, Plantation("indigo", True))
    state = with_buildings(state, player, OwnedBuilding("small_indigo_plant", 1))
    state = replace(state, goods_supply=(10, 0, 11, 9, 9))
    assert "privilege indigo" not in [
        GAME.format_action(action)
        for action in craftsman_actions(state, state.players[player])
    ]
