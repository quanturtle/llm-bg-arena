"""Tests for Puerto Rico phase ends, round ends, the game end and the winner."""

from dataclasses import replace

from boardgames.games.puerto_rico import PuertoRicoConfig
from boardgames.games.puerto_rico.model import (
    OwnedBuilding,
    RoleState,
    city_spaces_used,
    replace_role,
)
from boardgames.games.puerto_rico.rounds import (
    check_end_game,
    compute_winner,
    end_round,
    finish_standard_phase,
    refill_colonist_ship,
    tiebreak_key,
)
from tests.games.puerto_rico.support import (
    GAME,
    play,
    start,
    with_buildings,
    with_doubloons,
    with_goods,
)


def test_settler_draws_leftover_deck_before_reshuffling_discards() -> None:
    state = start(seed=3)
    state = replace(
        state,
        active_role="settler",
        face_up=(),
        plantation_deck=("coffee",),
        plantation_discard=("corn", "corn", "corn"),
    )
    state = finish_standard_phase(state)[0]
    assert state.face_up[0] == "coffee"
    assert state.face_up[1:] == ("corn", "corn", "corn")


def test_short_colonist_refill_is_announced_and_observed() -> None:
    state = replace(
        start(seed=5),
        active_role="mayor",
        phase="mayor_action",
        colonist_supply=0,
        colonist_ship=0,
    )
    state, events = finish_standard_phase(state)
    assert state.colonist_shortage
    assert any(event.kind == "colonist_shortage" for event in events)
    observation = GAME.observe(state, None)
    assert observation.data["colonist_shortage"] is True


def test_full_trading_house_is_cleared_at_phase_end() -> None:
    state = start(seed=10)
    before = list(state.goods_supply)
    state = replace(
        state,
        active_role="trader",
        phase="trader_action",
        trading_house=("indigo", "sugar", "corn", "coffee"),
    )
    state = finish_standard_phase(state)[0]
    assert state.trading_house == ()
    expected = list(before)
    expected[0] += 1  # corn
    expected[1] += 1  # indigo
    expected[2] += 1  # sugar
    expected[4] += 1  # coffee
    assert list(state.goods_supply) == expected


def test_end_game_when_victory_point_supply_runs_out() -> None:
    state = replace(start(seed=1), vp_supply=0)
    ended = check_end_game(state)
    assert ended.phase == "game_over"
    assert ended.end_reason == "victory point supply exhausted"
    assert ended.winner is not None
    assert GAME.is_terminal(ended)


def test_end_game_only_when_the_mayor_cannot_refill_the_ship() -> None:
    state = replace(start(seed=1), colonist_supply=0, colonist_ship=0)
    assert check_end_game(state).end_reason is None
    ended = check_end_game(refill_colonist_ship(state))
    assert ended.end_reason == "colonist supply exhausted"


def test_exact_colonist_refill_does_not_end_the_game() -> None:
    state = replace(start(seed=1), colonist_supply=3)
    refilled = refill_colonist_ship(state)
    assert refilled.colonist_ship == 3
    assert not refilled.colonist_shortage
    assert check_end_game(refilled).end_reason is None


def test_end_game_when_a_city_is_full() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("guild_hall", 0),
        OwnedBuilding("residence", 0),
        OwnedBuilding("fortress", 0),
        OwnedBuilding("customs_house", 0),
        OwnedBuilding("city_hall", 0),
        OwnedBuilding("small_market", 0),
        OwnedBuilding("small_indigo_plant", 0),
    )
    assert city_spaces_used(state.players[player]) == 12
    ended = check_end_game(state)
    assert ended.end_reason == "a player's city is full"


def test_round_limit_ends_the_game() -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=1)
    state = GAME.setup(config, 4).state
    ended = end_round(state)
    assert ended.round == 2
    assert ended.phase == "game_over"
    assert ended.end_reason == "round limit reached"


def test_winner_breaks_ties_by_doubloons_and_goods() -> None:
    state = start(seed=1)
    p1, p2 = state.order[0], state.order[1]
    state = with_doubloons(state, p1, 4)
    state = with_doubloons(state, p2, 5)
    assert compute_winner(state) == p2
    state = with_goods(state, p1, corn=2)
    assert compute_winner(state) == p1


def test_final_tie_uses_the_last_rounds_governor() -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=1)
    state = GAME.setup(config, 4).state
    final_governor = state.governor
    ended = end_round(state)
    assert ended.phase == "game_over"
    assert ended.final_governor == final_governor
    assert ended.winner == final_governor


def test_role_doubloons_and_governor_rotation() -> None:
    state = start(seed=3)
    governor = state.governor
    state = replace_role(
        state, "settler", RoleState("settler", doubloons=2, taken_by=None)
    )
    state = play(state, "role settler")
    assert state.players[governor].doubloons == 2 + 2
    next_governor = state.order[1]
    assert end_round(state).governor == next_governor


def test_ship_refill_uses_empty_building_slots_above_the_player_count() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("indigo_plant", 0),
        OwnedBuilding("sugar_mill", 0),
    )
    state = replace(state, colonist_supply=50)
    refilled = refill_colonist_ship(state)
    assert refilled.colonist_ship == 6
    assert refilled.colonist_supply == 44


def test_governor_tie_break_prefers_the_closer_seat() -> None:
    state = start(seed=1)
    governor = state.governor
    next_seat = state.order[1]
    assert tiebreak_key(state, governor)[1] == 0
    assert tiebreak_key(state, next_seat)[1] < 0
