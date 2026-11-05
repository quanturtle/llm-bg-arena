from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.catan import (
    BuyDev,
    CatanConfig,
    PlaceRoad,
    PlayKnight,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
)
from boardgames.games.catan.model import (
    DEV_COST,
    MAX_ROADS,
    dev_hand_from,
    empty_dev_hand,
    empty_hand,
    hand_from,
    hand_total,
)
from tests.games.catan.support import (
    GAME,
    P1,
    P2,
    action_state,
    listing,
    path_edges,
    play_setup,
    set_hand,
)


def test_knight_moves_robber_and_counts_for_largest_army() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
    )
    knight = next(action for action in listing(armed) if isinstance(action, PlayKnight))
    transition = GAME.apply(armed, P1, knight)
    after = transition.state
    assert after.robber == knight.hex
    assert after.knights_played[P1] == 1
    assert after.dev_hands[P1] == empty_dev_hand()
    assert after.dev_played_this_turn is True
    assert not any(isinstance(action, PlayKnight) for action in listing(after))


def test_road_building_places_two_free_roads() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(road_building=1), empty_dev_hand(), empty_dev_hand()),
    )
    playing = GAME.apply(armed, P1, PlayRoadBuilding()).state
    assert playing.phase == "free_road"
    assert playing.free_roads == 2
    first = next(action for action in listing(playing) if isinstance(action, PlaceRoad))
    after_first = GAME.apply(playing, P1, first).state
    assert after_first.roads[first.edge] == P1
    assert after_first.free_roads == 1
    second = next(
        action for action in listing(after_first) if isinstance(action, PlaceRoad)
    )
    after_second = GAME.apply(after_first, P1, second).state
    assert after_second.phase == "actions"
    assert after_second.free_roads == 0


def test_year_of_plenty_and_monopoly() -> None:
    state, _ = play_setup()
    plenty = replace(
        state,
        phase="actions",
        dice=(1, 2),
        hands=(empty_hand(), empty_hand(), empty_hand()),
        dev_hands=(dev_hand_from(year_of_plenty=1), empty_dev_hand(), empty_dev_hand()),
    )
    after_plenty = GAME.apply(plenty, P1, PlayYearOfPlenty("wood", "ore")).state
    assert after_plenty.hands[P1] == hand_from(wood=1, ore=1)
    assert after_plenty.dev_hands[P1] == empty_dev_hand()

    monopoly = replace(
        state,
        phase="actions",
        dice=(1, 2),
        hands=(empty_hand(), hand_from(wood=3), empty_hand()),
        dev_hands=(dev_hand_from(monopoly=1), empty_dev_hand(), empty_dev_hand()),
    )
    after_monopoly = GAME.apply(monopoly, P1, PlayMonopoly("wood")).state
    assert after_monopoly.hands[P1] == hand_from(wood=3)
    assert after_monopoly.hands[P2] == empty_hand()


def test_buying_a_victory_point_card_can_win() -> None:
    config = CatanConfig(num_players=3, victory_points=3)
    state, _ = play_setup(config)
    funded = action_state(set_hand(state, P1, DEV_COST))
    rigged = replace(funded, dev_deck=("victory_point",), dev_hands=state.dev_hands)
    transition = GAME.apply(rigged, P1, BuyDev())
    assert transition.state.phase == "game_over"
    assert transition.state.winner == P1
    assert GAME.scores(transition.state).points[P1] == 3
    assert hand_total(transition.state.dev_hands[P1]) == 1


def test_bought_cards_cannot_be_played_the_same_turn() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
        dev_bought=dev_hand_from(knight=1),
    )
    assert [action for action in listing(armed) if isinstance(action, PlayKnight)] == []


def test_road_building_stops_after_the_last_piece() -> None:
    state, _ = play_setup()
    path = path_edges(MAX_ROADS - 1)
    roads: list[PlayerId | None] = [None] * 72
    for edge in path:
        roads[edge] = P1
    armed = replace(
        state,
        roads=tuple(roads),
        phase="actions",
        dice=(1, 2),
        active=P1,
        dev_hands=(
            dev_hand_from(road_building=1),
            empty_dev_hand(),
            empty_dev_hand(),
        ),
    )
    playing = GAME.apply(armed, P1, PlayRoadBuilding()).state
    free_road = next(
        action for action in listing(playing) if isinstance(action, PlaceRoad)
    )
    after = GAME.apply(playing, P1, free_road).state
    assert after.phase == "actions"
    assert after.free_roads == 0


def test_only_one_development_card_can_be_played_per_turn() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(
            dev_hand_from(knight=1, year_of_plenty=1),
            empty_dev_hand(),
            empty_dev_hand(),
        ),
    )
    knight = next(action for action in listing(armed) if isinstance(action, PlayKnight))
    after = GAME.apply(armed, P1, knight).state
    assert not any(isinstance(action, PlayYearOfPlenty) for action in listing(after))
