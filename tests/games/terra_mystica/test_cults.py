"""Tests for Terra Mystica cult actions: sending priests and the cult-top limits."""

from dataclasses import replace

from boardgames.core import seats
from boardgames.games.terra_mystica import AdvanceCult, SendPriest
from boardgames.games.terra_mystica.constants import Cult
from boardgames.games.terra_mystica.model import cult_limit, replace_player
from tests.games.terra_mystica.support import (
    GAME,
    listing,
    play_setup,
    start,
    with_resources,
)


def test_send_priest_costs_a_priest_and_advances_cult() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, priests=1)
    before = state.players[player].cult(Cult.FIRE)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, SendPriest) and action.cult is Cult.FIRE
    )
    state = GAME.apply(state, player, action).state
    assert state.players[player].resources.priests == 0
    assert state.players[player].cult(Cult.FIRE) > before
    assert state.used_orders[(action.cult, action.order)] == player


def test_cult_order_spaces_are_shared() -> None:
    state = play_setup(start(num_players=2, seed=2))
    first = state.active_player
    second = next(seat for seat in seats(2) if seat != first)
    state = with_resources(state, first, priests=1)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, SendPriest)
        and action.cult is Cult.FIRE
        and action.order == 0
    )
    state = GAME.apply(state, first, action).state
    assert state.used_orders[(Cult.FIRE, 0)] == first
    state = with_resources(state, second, priests=1)
    state = replace(state, active_player=second)
    assert not any(
        isinstance(action, SendPriest)
        and action.cult is Cult.FIRE
        and action.order == 0
        for action in listing(state)
    )


def test_advance_cult_costs_a_priest() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, priests=1)
    action = next(
        action for action in listing(state) if isinstance(action, AdvanceCult)
    )
    before = state.players[player].cult(action.cult)
    state = GAME.apply(state, player, action).state
    assert state.players[player].resources.priests == 0
    assert state.players[player].cult(action.cult) == before + 1


def test_cult_space_ten_requires_a_key() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    owner = state.players[player]
    owner = owner.with_cult(Cult.EARTH, 9)
    owner = replace(owner, resources=replace(owner.resources, priests=1))
    state = replace_player(state, player, owner)
    assert cult_limit(state.players[player]) == 9
    assert not any(
        isinstance(action, AdvanceCult) and action.cult is Cult.EARTH
        for action in listing(state)
    )
    assert any(
        isinstance(action, SendPriest) and action.cult is Cult.EARTH
        for action in listing(state)
    )
    owner = replace(state.players[player], keys=1)
    state = replace_player(state, player, owner)
    assert cult_limit(state.players[player]) == 10
    assert any(
        action.cult is Cult.EARTH
        for action in listing(state)
        if isinstance(action, AdvanceCult)
    )


def test_second_player_cannot_enter_an_occupied_cult_top() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    other = next(seat for seat in seats(2) if seat != player)
    owner = state.players[player].with_cult(Cult.FIRE, 9)
    owner = replace(owner, keys=1, resources=replace(owner.resources, priests=1))
    state = replace_player(state, player, owner)
    other_owner = state.players[other].with_cult(Cult.FIRE, 10)
    state = replace_player(state, other, other_owner)
    assert not any(
        isinstance(action, AdvanceCult) and action.cult is Cult.FIRE
        for action in listing(state)
    )
    assert any(
        isinstance(action, SendPriest) and action.cult is Cult.FIRE
        for action in listing(state)
    )


def test_priest_can_block_an_order_space_on_a_full_track() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    owner = state.players[player].with_cult(Cult.EARTH, 9)
    owner = replace(owner, resources=replace(owner.resources, priests=1))
    state = replace_player(state, player, owner)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, SendPriest) and action.cult is Cult.EARTH
    )
    after = GAME.apply(state, player, action).state
    assert after.players[player].cult(Cult.EARTH) == 9
    assert after.used_orders[(Cult.EARTH, action.order)] == player
    assert after.players[player].resources.priests == 0
