from dataclasses import replace

from boardgames.core import JsonObject, Rng
from boardgames.core.json_data import json_object, list_of_values
from boardgames.games.catan import (
    BuyDev,
    CatanConfig,
    PlaceRoad,
    PlaceSettlement,
    PlayRoadBuilding,
)
from boardgames.games.catan.geometry import HEX_VERTICES, VERTEX_EDGES
from boardgames.games.catan.model import (
    DEV_COST,
    dev_hand_from,
    empty_dev_hand,
    empty_hand,
    hand_from,
)
from tests.games.catan.support import (
    GAME,
    P1,
    P2,
    action_state,
    play_setup,
    set_hand,
)


def test_victory_point_cards_are_hidden_from_opponents() -> None:
    state, _ = play_setup()
    hidden = replace(
        state,
        dev_hands=(dev_hand_from(victory_point=1), empty_dev_hand(), empty_dev_hand()),
    )
    public = GAME.observe(hidden, P2).data
    own = json_object(GAME.observe(hidden, P1).data, "you")
    points = number_values(public, "public_points")
    assert points[P1] == 2
    assert own["points"] == 3
    assert GAME.public_scores(hidden).points[P1] == 2
    assert GAME.scores(hidden).points[P1] == 3


def test_observation_ignores_other_players_hidden_cards() -> None:
    state, _ = play_setup()
    viewer = P2
    original = replace(
        state,
        phase="actions",
        hands=(hand_from(wood=3), hand_from(ore=2), empty_hand()),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
    )
    changed = replace(
        original,
        hands=(hand_from(ore=3), hand_from(ore=2), empty_hand()),
        dev_hands=(dev_hand_from(victory_point=1), empty_dev_hand(), empty_dev_hand()),
        dev_deck=tuple(reversed(original.dev_deck)),
        rng=Rng(original.rng.state + 1),
    )
    for observer in (viewer, None):
        assert GAME.observe(original, observer) == GAME.observe(changed, observer)
        assert GAME.render_text(GAME.observe(original, observer)) == GAME.render_text(
            GAME.observe(changed, observer)
        )


def test_render_text_and_descriptions_name_the_board() -> None:
    state, _ = play_setup()
    observation = GAME.observe(action_state(state), P1)
    text = GAME.render_text(observation)
    assert "You are P1." in text
    assert "Hexes:" in text
    assert "Intersections:" in text
    assert "Paths:" in text
    assert "Your hand:" in text
    vertex = HEX_VERTICES[0][0]
    described = GAME.describe_action(observation, PlaceSettlement(vertex))
    assert f"v{vertex}" in described
    edge = VERTEX_EDGES[vertex][0]
    assert f"e{edge}" in GAME.describe_action(observation, PlaceRoad(edge))


def test_game_over_render_shows_final_points_and_revealed_cards() -> None:
    config = CatanConfig(num_players=3, victory_points=3)
    state, _ = play_setup(config)
    funded = action_state(set_hand(state, P1, DEV_COST))
    rigged = replace(funded, dev_deck=("victory_point",), dev_hands=state.dev_hands)
    over = GAME.apply(rigged, P1, BuyDev()).state
    text = GAME.render_text(GAME.observe(over, P2))
    assert "  P1: 3 VP (settlements 2, victory cards 1);" in text
    assert "Revealed hands:" in text
    assert "development cards: knight 0, roadbuilding 0, yearofplenty 0, " in text
    assert "monopoly 0, victorypoint 1." in text


def test_render_and_rules_name_development_cards_as_notation_does() -> None:
    state, _ = play_setup()
    armed = action_state(
        replace(
            state,
            dev_hands=(
                dev_hand_from(road_building=1),
                empty_dev_hand(),
                empty_dev_hand(),
            ),
        )
    )
    observation = GAME.observe(armed, P1)
    text = GAME.render_text(observation)
    rules = GAME.rules_text()
    assert "Your development cards: knight 0, roadbuilding 1, yearofplenty 0" in text
    assert "roadbuilding" in GAME.describe_action(observation, PlayRoadBuilding())
    for name in ("knight", "roadbuilding", "yearofplenty", "monopoly", "victorypoint"):
        assert f"`{name}`" in rules
    for spelling in ("road_building", "Road Building", "Year of Plenty"):
        assert spelling not in text
        assert spelling not in rules


def test_observation_and_render_show_the_development_deck_size() -> None:
    state, _ = play_setup()
    shorter = replace(state, dev_deck=state.dev_deck[:7])
    for viewer in (P1, None):
        observation = GAME.observe(shorter, viewer)
        assert observation.data["dev_deck_size"] == 7
        assert "Development deck: 7 cards left." in GAME.render_text(observation)


def number_values(data: JsonObject, key: str) -> list[float]:
    """A JSON list of numbers, as floats."""
    return [
        float(value)
        for value in list_of_values(key, data[key])
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]
