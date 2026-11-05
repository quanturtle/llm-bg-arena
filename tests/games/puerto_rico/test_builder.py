"""Tests for the Puerto Rico Builder and the University."""

from boardgames.games.puerto_rico.model import OwnedBuilding
from tests.games.puerto_rico.support import (
    drain,
    notations,
    play,
    select_role,
    start,
    with_buildings,
    with_doubloons,
    with_quarries,
)


def test_builder_builds_with_privilege_discount() -> None:
    state = start(seed=6)
    chooser = state.order[0]
    state = with_doubloons(state, chooser, 10)
    state = select_role(state, "builder")
    assert state.phase == "builder_action"
    assert "build small_indigo_plant" in notations(state)
    state = play(state, "build small_indigo_plant")
    owner = state.players[chooser]
    assert owner.owns("small_indigo_plant")
    assert owner.doubloons == 10  # cost 1 minus the Builder's doubloon
    assert state.available_buildings.count("small_indigo_plant") == 3
    state = drain(state)
    assert state.phase == "role_selection"


def test_builder_quarry_discount_and_university() -> None:
    state = start(seed=6)
    chooser = state.order[0]
    state = with_doubloons(state, chooser, 10)
    state = with_quarries(state, chooser, quarries=2, occupied=2)
    state = with_buildings(state, chooser, OwnedBuilding("university", 1))
    before_supply = state.colonist_supply
    state = select_role(state, "builder")
    state = play(state, "build sugar_mill")
    owner = state.players[chooser]
    assert owner.owns("sugar_mill")
    assert owner.doubloons == 9  # 4 - 2 quarries - 1 Builder discount
    new_building = owner.buildings[-1]
    assert new_building.name == "sugar_mill"
    assert new_building.colonists == 1
    assert state.colonist_supply == before_supply - 1


def test_university_colonist_is_optional() -> None:
    state = start(seed=6)
    player = state.order[0]
    state = with_doubloons(state, player, 10)
    state = with_buildings(state, player, OwnedBuilding("university", 1))
    state = select_role(state, "builder")
    assert "build small_indigo_plant nouniversity" in notations(state)
    state = play(state, "build small_indigo_plant nouniversity")
    assert state.players[player].buildings[-1].colonists == 0
