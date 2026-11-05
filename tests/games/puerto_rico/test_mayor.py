"""Tests for the Puerto Rico Mayor and the bonus colonist supply."""

from dataclasses import replace

from boardgames.games.puerto_rico import SelectRole
from boardgames.games.puerto_rico.model import OwnedBuilding, Plantation, role_chooser
from tests.games.puerto_rico.support import (
    GAME,
    drain,
    notations,
    play,
    select_role,
    start,
    with_buildings,
    with_colonists,
    with_doubloons,
    with_plantations,
)


def test_mayor_event_omits_the_extra_colonist_when_the_supply_is_empty() -> None:
    state = replace(start(seed=5), colonist_supply=0, colonist_ship=3)
    player = state.active_player
    transition = GAME.apply(state, player, SelectRole("mayor"))
    event = next(
        event for event in transition.events if event.kind == "colonists_distributed"
    )
    assert "no extra colonist" in event.text
    assert "takes the extra colonist" not in event.text


def test_mayor_distributes_colonists_and_refills_the_ship() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    assert state.phase == "mayor_action"
    assert state.colonist_ship == 0
    chooser = state.active_player
    assert state.players[chooser].colonists_unplaced >= 2
    state = drain(state)
    assert state.phase == "role_selection"
    assert state.colonist_ship == 3
    assert role_chooser(state, "mayor") == chooser


def test_mayor_place_and_pick_up_colonists() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 1)
    # Place on the starting plantation, then pick it back up.
    state = play(state, "place plantation 0")
    assert state.players[player].plantations[0].colonized
    assert state.players[player].colonists_unplaced == 0
    assert "pick plantation 0" in notations(state)
    state = play(state, "pick plantation 0")
    assert not state.players[player].plantations[0].colonized
    assert state.players[player].colonists_unplaced == 1


def test_mayor_closes_when_no_placement_targets_remain() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 0)
    state = with_plantations(state, player, Plantation("corn", True))
    assert "finish" in notations(state)


def test_mayor_places_new_colonists_before_moving_existing_ones() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 2)
    state = with_plantations(
        state,
        player,
        Plantation("corn", True),
        Plantation("indigo", False),
        Plantation("sugar", False),
    )
    assert not any(option.startswith("pick ") for option in notations(state))
    state = play(state, "place plantation 1")
    state = play(state, "place plantation 2")
    assert state.players[player].colonists_unplaced == 0
    assert "pick plantation 0" in notations(state)


def test_hospice_and_university_use_the_ship_when_the_supply_is_empty() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    state = replace(state, colonist_supply=0, colonist_ship=3)
    state = select_role(state, "settler")
    take = next(
        option
        for option in notations(state)
        if option.startswith("take ") and option != "take quarry"
    )
    state = play(state, take)
    assert state.players[player].plantations[-1].colonized
    assert state.colonist_ship == 2

    state = start(seed=6)
    player = state.order[0]
    state = with_doubloons(state, player, 10)
    state = with_buildings(state, player, OwnedBuilding("university", 1))
    state = replace(state, colonist_supply=0, colonist_ship=3)
    state = select_role(state, "builder")
    state = play(state, "build small_indigo_plant")
    assert state.players[player].buildings[-1].colonists == 1
    assert state.colonist_ship == 2
