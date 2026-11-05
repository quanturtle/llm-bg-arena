"""Tests for Terra Mystica round flow: passing, income and the round-end cult bonus."""

from dataclasses import replace

from boardgames.games.terra_mystica import Building, Hex
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    ScoringAction,
    ScoringTile,
)
from boardgames.games.terra_mystica.rounds import end_round, income_for
from tests.games.terra_mystica.support import (
    GAME,
    P1,
    action_state,
    empty_land_tiles,
    play,
    play_setup,
    start,
)


def test_pass_awards_starting_player_and_advances_round() -> None:
    state = play_setup(start(num_players=3, seed=4, rounds=2))
    first_passer = state.active_player
    while state.round == 1 and state.phase == "action":
        state = play(state, "pass")
    assert state.round == 2
    assert state.order[0] == first_passer
    assert state.phase == "action"


def test_game_ends_after_final_round_with_scores() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=1))
    while not GAME.is_terminal(state):
        state = play(state, "pass")
    assert GAME.pending_decisions(state) == ()
    scores = GAME.scores(state)
    assert len(scores.points) == 2
    assert all(points >= 0 for points in scores.points.values())
    assert scores.breakdown


def test_priest_supply_caps_cult_bonuses() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = replace(state, scoring=(priest_tile, priest_tile))
    first, second = state.order
    state = replace(
        state,
        used_orders={(Cult.FIRE, 0): first, (Cult.WATER, 0): second},
        players=tuple(
            replace(
                player,
                cults=(9, 9, 9, 9),
                resources=replace(player.resources, priests=6),
            )
            for player in state.players
        ),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    assert state.round == 2
    assert all(player.resources.priests == 6 for player in state.players)


def test_engineers_eighth_dwelling_pays_six_workers() -> None:
    state = start(num_players=2, seed=1)
    positions = empty_land_tiles(state)[:8]
    board = state.board
    for position in positions:
        board = board.place(position, Building(BuildingType.DWELLING, P1))
    owner = replace(state.players[P1], faction=FactionType.ENGINEERS)
    assert income_for(board, P1, owner).workers == 6


def test_standard_trading_house_and_temple_income() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    position = Hex(0, 0)
    state = action_state(
        state,
        player,
        (position, BuildingType.TRADING_HOUSE),
        (position.neighbours()[0], BuildingType.TEMPLE),
    )
    owner = replace(state.players[player], faction=FactionType.WITCHES)
    income = income_for(state.board, player, owner)
    assert (income.coins, income.power, income.priests) == (2, 1, 1)
    return


def test_no_cult_bonus_after_the_final_round() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=1))
    state = replace(
        state,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
        players=tuple(replace(player, cults=(9, 9, 9, 9)) for player in state.players),
    )
    before = [player.resources.priests for player in state.players]
    transition = end_round(state, ())
    assert transition.state.phase == "game_over"
    assert [player.resources.priests for player in transition.state.players] == before
    assert all(event.kind != "cult_bonus" for event in transition.events)
    return
