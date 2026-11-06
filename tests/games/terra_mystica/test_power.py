"""Tests for Terra Mystica power actions and the Alchemists' trades."""

from dataclasses import replace

from boardgames.games.terra_mystica import PowerAction, TradeCoinsForVp, TradeVpForCoin
from boardgames.games.terra_mystica.constants import FactionType, Resources
from boardgames.games.terra_mystica.model import replace_player
from tests.games.terra_mystica.support import (
    GAME,
    listing,
    play_setup,
    start,
    with_resources,
)


def test_power_actions_spend_bowl_three_power() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, power1=0, power2=0, power3=12)
    action = next(
        action for action in listing(state) if isinstance(action, PowerAction)
    )
    state = GAME.apply(state, player, action).state
    assert state.players[player].resources.power3 < 12
    assert action.kind in state.used_power_actions


def test_power_action_reports_burned_tokens() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, power1=5, power2=7, power3=0)
    transition = GAME.apply(state, player, PowerAction("priest"))
    event = next(event for event in transition.events if event.kind == "power_action")
    assert event.data["burned"] == 3
    assert "burned 3 tokens" in event.text
    assert "spent 3 power for a priest" in event.text


def test_alchemists_trade_vp_and_coins_without_ending_the_turn() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.ALCHEMISTS,
            victory_points=20,
            resources=Resources(coins=4, workers=5, priests=1),
        ),
    )
    assert TradeVpForCoin() in listing(state)
    assert TradeCoinsForVp() in listing(state)
    state = GAME.apply(state, player, TradeVpForCoin()).state
    owner = state.players[player]
    assert owner.victory_points == 19 and owner.resources.coins == 5
    assert state.phase == "action" and state.active_player == player
    state = GAME.apply(state, player, TradeCoinsForVp()).state
    owner = state.players[player]
    assert owner.victory_points == 20 and owner.resources.coins == 3
