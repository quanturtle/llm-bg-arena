"""Tests for the Puerto Rico Settler: plantations, quarries, Hospice and Hacienda."""

from dataclasses import replace

from boardgames.games.puerto_rico import Pass, TakePlantation, TakeQuarry, UseHacienda
from boardgames.games.puerto_rico.model import OwnedBuilding, Plantation, role_chooser
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


def test_settler_role_takes_a_plantation_and_refreshes_face_up() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = select_role(state, "settler")
    assert state.phase == "settler_action"
    assert state.active_role == "settler"
    assert state.active_player == governor
    options = notations(state)
    assert "take quarry" in options  # the role chooser's privilege
    choice = next(
        option
        for option in options
        if option.startswith("take ") and option != "take quarry"
    )
    good = choice.split()[1]
    state = play(state, choice)
    assert len(state.players[governor].plantations) == 2
    assert state.players[governor].plantations[-1].good == good
    assert not state.players[governor].plantations[-1].colonized
    state = drain(state)
    assert state.phase == "role_selection"
    assert len(state.face_up) == 4
    assert role_chooser(state, "settler") == governor


def test_settler_privilege_can_take_a_quarry() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = select_role(state, "settler")
    before_supply = state.quarry_supply
    state = play(state, "take quarry")
    owner = state.players[governor]
    assert owner.quarries == 1
    assert owner.occupied_quarries == 0
    assert state.quarry_supply == before_supply - 1


def test_construction_hut_lets_another_player_take_a_quarry() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = select_role(state, "settler")
    state = play(state, "pass")
    other = state.active_player
    assert other != governor
    state = with_buildings(state, other, OwnedBuilding("construction_hut", 1))
    assert "take quarry" in notations(state)
    state = play(state, "take quarry")
    assert state.players[other].quarries == 1


def test_hospice_colonizes_a_taken_plantation() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = with_buildings(state, governor, OwnedBuilding("hospice", 1))
    state = select_role(state, "settler")
    before_supply = state.colonist_supply
    options = [
        option
        for option in notations(state)
        if option.startswith("take ") and option != "take quarry"
    ]
    state = play(state, options[0])
    plantation = state.players[governor].plantations[-1]
    assert plantation.colonized
    assert state.colonist_supply == before_supply - 1


def test_hacienda_draws_an_extra_plantation_once() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = with_buildings(state, governor, OwnedBuilding("hacienda", 1))
    state = select_role(state, "settler")
    before_deck = len(state.plantation_deck)
    before_plantations = len(state.players[governor].plantations)
    state = play(state, "hacienda")
    assert len(state.plantation_deck) == before_deck - 1
    assert len(state.players[governor].plantations) == before_plantations + 1
    assert state.players[governor].hacienda_used
    assert "hacienda" not in notations(state)


def test_hacienda_can_draw_when_only_the_discard_pile_remains() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = with_buildings(state, governor, OwnedBuilding("hacienda", 1))
    state = replace(
        state,
        plantation_deck=(),
        plantation_discard=("coffee", "coffee"),
    )
    state = select_role(state, "settler")
    assert "hacienda" in notations(state)
    state = play(state, "hacienda")
    owner = state.players[governor]
    assert owner.plantations[-1].good == "coffee"
    assert state.plantation_discard == ()
    assert state.plantation_deck == ("coffee",)


def test_settler_keeps_unchosen_plantations_in_a_discard_pile() -> None:
    state = start(seed=3)
    state = select_role(state, "settler")
    taken = state.face_up[0]
    unchosen = state.face_up[1:]
    state = play(state, f"take {taken}")
    while state.phase == "settler_action":
        state = play(state, "pass")
    assert state.plantation_discard == unchosen
    assert len(state.face_up) == 4


def test_hospice_colonizes_a_taken_quarry() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    before = state.colonist_supply
    state = select_role(state, "settler")
    state = play(state, "take quarry")
    owner = state.players[player]
    assert owner.quarries == 1
    assert owner.occupied_quarries == 1
    assert state.colonist_supply == before - 1


def test_hospice_colonist_is_optional() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    before = state.colonist_supply
    state = select_role(state, "settler")
    take = next(
        option
        for option in notations(state)
        if option.startswith("take ") and option.endswith("nohospice")
    )
    state = play(state, take)
    assert not state.players[player].plantations[-1].colonized
    assert state.colonist_supply == before


def test_hospice_quarry_colonist_is_optional() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    state = select_role(state, "settler")
    assert "take quarry nohospice" in notations(state)
    state = play(state, "take quarry nohospice")
    assert state.players[player].occupied_quarries == 0


def test_declining_a_bonus_colonist_with_none_left_is_explained() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("hospice", 1),
        OwnedBuilding("university", 1),
    )
    state = replace(state, colonist_supply=0, colonist_ship=0)
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(TakePlantation(state.face_up[0], use_hospice=False))
        == "There is no colonist available to place."
    )


def test_settler_refill_and_reshuffle_emit_events() -> None:
    state = start(seed=3)
    state = select_role(state, "settler")
    kinds: list[str] = []
    while state.phase == "settler_action":
        (decision,) = GAME.pending_decisions(state)
        transition = GAME.apply(state, decision.player, Pass())
        kinds.extend(event.kind for event in transition.events)
        state = transition.state
    assert "face_up_refilled" in kinds

    state = start(seed=3)
    state = replace(
        state,
        active_role="settler",
        phase="settler_action",
        face_up=(),
        plantation_deck=(),
        plantation_discard=("coffee", "coffee", "coffee", "coffee"),
        players_acted=frozenset(state.order[:-1]),
        active_player=state.order[-1],
    )
    transition = GAME.apply(state, state.order[-1], Pass())
    kinds = [event.kind for event in transition.events]
    assert "plantation_discard_reshuffled" in kinds


def test_hacienda_reshuffle_emits_an_event() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hacienda", 1))
    state = replace(
        state,
        plantation_deck=(),
        plantation_discard=("coffee", "coffee"),
    )
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    transition = GAME.apply(state, decision.player, UseHacienda())
    assert next(event.kind for event in transition.events) == (
        "plantation_discard_reshuffled"
    )


def test_take_quarry_explains_a_full_island_before_the_privilege() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_plantations(state, player, *(Plantation("corn") for _ in range(12)))
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert space.explain(TakeQuarry()) == "Your island is full."
