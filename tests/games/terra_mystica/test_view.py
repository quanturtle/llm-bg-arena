"""Tests for the Terra Mystica observation, text rendering and action descriptions."""

from dataclasses import replace

from boardgames.core import Event, PlayerId, seat_label
from boardgames.games.terra_mystica import (
    BuildDwelling,
    Hex,
    PowerAction,
    SkipCultSpade,
    UseCultSpade,
)
from boardgames.games.terra_mystica.constants import FactionType, Terrain
from boardgames.games.terra_mystica.model import replace_at, replace_player
from tests.games.terra_mystica.support import (
    GAME,
    P1,
    listing,
    play_setup,
    start,
    with_resources,
)


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
    assert "power bowls I:" in text
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


def test_power_action_description_reports_burned_tokens() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, power1=5, power2=7, power3=0)
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, PowerAction("priest"))
    assert "Spend 3 power for a priest" in description
    assert "burn 6 Bowl II tokens" in description
    assert "permanently lose 3 tokens" in description
    state = with_resources(state, player, power1=5, power2=7, power3=2)
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, PowerAction("priest"))
    assert "permanently lose 1 token" in description


def test_fakir_flight_is_called_a_carpet_flight() -> None:
    state = play_setup(start(num_players=2, seed=1))
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.FAKIRS),
    )
    own = {
        tile.position
        for tile in state.board.tiles
        if tile.building is not None and tile.building.owner == player
    }
    target = next(
        tile
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and not any(neighbour in own for neighbour in tile.position.neighbours())
    )
    state = replace(state, phase="action", active_player=player)
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, BuildDwelling(target.position))
    assert "carpet flight 1 priest" in description
    assert "tunnel" not in description


def test_spade_build_does_not_charge_a_carpet_flight() -> None:
    state = play_setup(start(num_players=2, seed=1))
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.FAKIRS),
    )
    own = {
        tile.position
        for tile in state.board.tiles
        if tile.building is not None and tile.building.owner == player
    }
    target = next(
        tile
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and not any(neighbour in own for neighbour in tile.position.neighbours())
    )
    board = state.board.replace_tile(
        target.position, replace(target, terrain=Terrain.DESERT)
    )
    state = replace(
        state,
        board=board,
        phase="cult_spades",
        spade_return="action",
        spade_actor=player,
        power_spade_tiles=(target.position,),
        cult_spades=replace_at(state.cult_spades, player, 0),
        active_player=player,
    )
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, BuildDwelling(target.position))
    assert "carpet flight" not in description
    assert "priest" not in description


def test_build_description_names_terrain_and_transform_cost() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.SWARMLINGS),
    )
    tile = next(
        tile
        for tile in state.board.tiles
        if tile.is_land and tile.building is None and tile.terrain is Terrain.DESERT
    )
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, BuildDwelling(tile.position))
    assert "desert -> lake" in description
    assert "3 spades = 9 workers" in description
    assert "building 3 coins + 2 workers" in description
