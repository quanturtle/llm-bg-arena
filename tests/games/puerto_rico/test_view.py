"""Tests for Puerto Rico observations, text rendering and action descriptions."""

from dataclasses import replace

from boardgames.core import seats
from boardgames.games.puerto_rico import Build, SelectRole, TakePlantation, TakeQuarry
from boardgames.games.puerto_rico.model import OwnedBuilding, public_points
from tests.games.puerto_rico.support import (
    GAME,
    start,
    with_buildings,
    with_vp_chips,
)

P1, P2, P3 = seats(3)


def test_victory_point_chips_are_private_until_the_end() -> None:
    state = start(seed=1)
    p1, p2 = state.order[0], state.order[1]
    state = with_vp_chips(with_vp_chips(state, p1, 5), p2, 3)
    observation = GAME.observe(state, p2)
    data = observation.data
    players = data["players"]
    assert isinstance(players, list)
    for entry in players:
        assert isinstance(entry, dict)
        assert "vp_chips" not in entry
    you = data["you"]
    assert isinstance(you, dict)
    assert you["vp_chips"] == 3
    spectator = GAME.observe(state, None)
    assert spectator.data["you"] is None
    assert GAME.public_scores(state).points[p1] == GAME.scores(state).points[p1] - 5


def test_final_scores_are_revealed_at_game_over() -> None:
    state = start(seed=1)
    p1 = state.order[0]
    state = with_vp_chips(state, p1, 5)
    ended = replace(state, phase="game_over", winner=p1, end_reason="test")
    observation = GAME.observe(ended, state.order[1])
    players = observation.data["players"]
    assert isinstance(players, list)
    assert all(isinstance(entry, dict) and "vp_chips" in entry for entry in players)
    final = observation.data["final_scores"]
    assert isinstance(final, list)


def test_render_text_names_the_viewer() -> None:
    state = start(seed=1)
    text = GAME.render_text(GAME.observe(state, P2))
    assert "You are P2." in text
    assert "Roles:" in text
    assert "Face-up plantations:" in text
    spectator = GAME.render_text(GAME.observe(state, None))
    assert "You are" not in spectator


def test_describe_action_names_the_action() -> None:
    state = start(seed=1)
    observation = GAME.observe(state, state.order[0])
    assert "settler" in GAME.describe_action(observation, SelectRole("settler"))
    assert "indigo" in GAME.describe_action(observation, TakePlantation("indigo"))
    assert "quarry" in GAME.describe_action(observation, TakeQuarry())
    assert "small_indigo_plant" in GAME.describe_action(
        observation, Build("small_indigo_plant")
    )


def test_observation_exposes_visible_building_points_only() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("guild_hall", 1),
        OwnedBuilding("indigo_plant", 0),
    )
    data = GAME.observe(state, player).data
    assert "public_points" not in data
    players = data["players"]
    assert isinstance(players, list)
    entry = players[player]
    assert isinstance(entry, dict)
    assert entry["building_points"] == 6
    assert entry["public_points"] == public_points(state.players[player])
