"""Tests for the Terra Mystica observation, text rendering and action descriptions."""

from dataclasses import replace

from boardgames.core import Event, PlayerId, seat_label
from boardgames.games.terra_mystica import Hex, SkipCultSpade, UseCultSpade
from boardgames.games.terra_mystica.model import replace_at
from tests.games.terra_mystica.support import GAME, P1, listing, start


def test_observation_is_public_and_renders() -> None:
    state = start(num_players=2, seed=1)
    spectator = GAME.observe(state, None)
    first = GAME.observe(state, P1)
    assert spectator.data["players"] == first.data["players"]
    assert spectator.data["board"] == first.data["board"]
    text = GAME.render_text(spectator)
    assert "Terra Mystica" not in text
    assert "Board:" in text
    assert "Round scoring:" in text
    assert "Legend:" in text


def test_observation_and_round_event_show_cult_bonuses() -> None:
    state = start(num_players=2, seed=1)
    observation = GAME.observe(state, None)
    bonuses = observation.data["scoring_bonuses"]
    assert isinstance(bonuses, list)
    assert len(bonuses) == 1
    assert isinstance(bonuses[0], dict)
    assert set(bonuses[0]) == {"cult", "per", "reward", "amount"}

    round_events: list[Event] = []
    while state.phase == "setup":
        (decision,) = GAME.pending_decisions(state)
        transition = GAME.apply(state, decision.player, listing(state)[0])
        state = transition.state
        round_events.extend(
            event for event in transition.events if event.kind == "round_started"
        )
    assert round_events
    assert "bonus" in round_events[0].data


def test_observation_and_text_show_passes_power_actions_and_cult_spades() -> None:
    state = start(num_players=2, seed=1, rounds=1)
    state = replace(
        state,
        passed=frozenset({PlayerId(1)}),
        pass_order=(PlayerId(1),),
        used_power_actions=frozenset({"coins"}),
    )
    observation = GAME.observe(state, None)
    data = observation.data
    assert data["pass_order"] == [1]
    assert data["used_power_actions"] == ["coins"]
    assert "home_terrains" not in data
    assert "active_cult_spades" not in data
    players = data["players"]
    assert isinstance(players, list)
    assert all("home_terrain" in player for player in players)
    text = GAME.render_text(observation)
    assert "Passed in order:" in text
    assert "Power actions used this round: coins." in text
    assert "home " in text
    assert "cult-bonus spade" not in text
    spade_state = replace(
        state,
        phase="cult_spades",
        cult_spades=(2, 2),
        active_player=PlayerId(0),
    )
    spade_text = GAME.render_text(GAME.observe(spade_state, None))
    assert "P1 has 2 cult-bonus spade(s)." in spade_text


def test_action_phase_spade_text_does_not_say_cult_bonus() -> None:
    state = start(num_players=2, seed=1, rounds=1)
    player = state.order[0]
    state = replace(
        state,
        phase="cult_spades",
        spade_return="action",
        spade_actor=player,
        cult_spades=replace_at(state.cult_spades, player, 2),
        active_player=player,
    )
    observation = GAME.observe(state, None)
    text = GAME.render_text(observation)
    assert f"{seat_label(player)} has 2 spade(s)." in text
    assert f"{seat_label(player)} has 2 cult-bonus spade(s)." not in text
    (decision,) = GAME.pending_decisions(state)
    assert "cult-bonus" not in decision.prompt
    assert "spade" in decision.prompt
    assert "cult-bonus" not in GAME.describe_action(
        observation, UseCultSpade(Hex(0, 0))
    )
    assert "cult-bonus" not in GAME.describe_action(observation, SkipCultSpade())
