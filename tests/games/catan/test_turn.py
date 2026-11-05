from dataclasses import replace

import pytest

from boardgames.core import IllegalActionError, Rng
from boardgames.games.catan import Building, Discard, MoveRobber, PlayKnight
from boardgames.games.catan.decisions import legal_action_list
from boardgames.games.catan.geometry import HEX_VERTICES
from boardgames.games.catan.model import (
    dev_hand_from,
    empty_dev_hand,
    empty_hand,
    hand_from,
    hand_total,
)
from boardgames.games.catan.rules import building_at
from boardgames.games.catan.turn import roll_dice
from tests.games.catan.support import GAME, P1, P2, listing, play_setup, start


def test_discard_is_private_and_then_the_robber_moves() -> None:
    state, _ = play_setup()
    state = replace(
        state,
        phase="discard",
        hands=(hand_from(wood=2), empty_hand(), empty_hand()),
        discard_remaining=(2, 0, 0),
    )
    (decision,) = GAME.pending_decisions(state)
    assert decision.player == P1
    first = GAME.apply(state, P1, Discard("wood"))
    assert first.state.discard_remaining == (1, 0, 0)
    assert first.state.phase == "discard"
    private = [event for event in first.events if isinstance(event.audience, frozenset)]
    assert len(private) == 1
    assert private[0].audience == frozenset({P1})
    second = GAME.apply(first.state, P1, Discard("wood")).state
    assert second.phase == "move_robber"
    assert GAME.pending_decisions(second)[0].kind == "move_robber"


def test_robber_steal_conserves_cards() -> None:
    state, _ = play_setup()
    p2_hexes = [
        hex_id
        for hex_id in range(len(state.hexes))
        if hex_id != state.robber
        and any(building_at(state, vertex) == P2 for vertex in HEX_VERTICES[hex_id])
    ]
    assert p2_hexes
    rigged = replace(
        state,
        phase="move_robber",
        hands=(empty_hand(), hand_from(wood=3), empty_hand()),
    )
    hex_id = p2_hexes[0]
    move = next(
        action
        for action in listing(rigged)
        if isinstance(action, MoveRobber)
        and action.hex == hex_id
        and action.victim == P2
    )
    transition = GAME.apply(rigged, P1, move)
    assert transition.state.robber == hex_id
    assert hand_total(transition.state.hands[P1]) == 1
    assert hand_total(transition.state.hands[P2]) == 2
    assert hand_total(rigged.hands[P1]) + hand_total(rigged.hands[P2]) == 3
    assert any(event.kind == "stolen" for event in transition.events)


def test_robber_must_change_hex() -> None:
    state, _ = play_setup()
    moving = replace(state, phase="move_robber")
    moves = [action for action in listing(moving) if isinstance(action, MoveRobber)]
    assert all(action.hex != state.robber for action in moves)
    with pytest.raises(IllegalActionError, match="already on that hex"):
        GAME.apply(moving, P1, MoveRobber(state.robber, None))


def test_robber_never_lists_the_mover_as_a_victim() -> None:
    state = start()
    hex_id = next(hex_id for hex_id in range(19) if hex_id != state.robber)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[hex_id][0]] = Building(P1, "settlement")
    moving = replace(
        state,
        phase="move_robber",
        buildings=tuple(buildings),
        hands=(hand_from(wood=1), empty_hand(), empty_hand()),
    )
    assert [a for a in listing(moving) if a.hex == hex_id] == [MoveRobber(hex_id, None)]
    armed = replace(
        moving,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
    )
    knights = [a for a in listing(armed) if isinstance(a, PlayKnight)]
    assert [a for a in knights if a.hex == hex_id] == [PlayKnight(hex_id, None)]
    with pytest.raises(IllegalActionError, match="steal from yourself"):
        GAME.apply(moving, P1, MoveRobber(hex_id, P1))


def seven_seed() -> int:
    for seed in range(1000):
        first, rng = Rng.seeded(seed).roll(6)
        second, _ = rng.roll(6)
        if first + second == 7:
            return seed
    raise AssertionError("no seed rolls seven")


def test_discard_amount_after_a_seven() -> None:
    seed = seven_seed()
    state = replace(
        start(),
        rng=Rng.seeded(seed),
        hands=(hand_from(wheat=9), hand_from(wood=7), empty_hand()),
    )
    transition = roll_dice(state, P1)
    assert transition.state.phase == "discard"
    assert transition.state.discard_remaining == (4, 0, 0)


def test_robbing_a_cardless_player_steals_nothing() -> None:
    state = start()
    hex_id = next(hex_id for hex_id in range(19) if hex_id != state.robber)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[hex_id][0]] = Building(P2, "settlement")
    state = replace(
        state,
        buildings=tuple(buildings),
        hands=(empty_hand(), empty_hand(), hand_from(wood=1)),
    )
    action = MoveRobber(hex_id, P2)
    state = replace(state, phase="move_robber")
    assert action in legal_action_list(state, P1)
    moved = GAME.apply(state, P1, action)
    assert moved.state.hands[P2] == empty_hand()
    assert moved.state.hands[P1] == empty_hand()
