from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.catan import (
    BuildCity,
    Building,
    BuyDev,
    PlaceRoad,
    PlaceSettlement,
)
from boardgames.games.catan.geometry import VERTEX_EDGES, VERTEX_NEIGHBORS
from boardgames.games.catan.model import (
    CITY_COST,
    MAX_SETTLEMENTS,
    ROAD_COST,
    SETTLEMENT_COST,
    empty_hand,
    hand_from,
)
from boardgames.games.catan.rules import (
    city_legal,
    legal_free_road_edges,
    settlement_pieces_available,
)
from tests.games.catan.support import (
    GAME,
    P1,
    P2,
    action_state,
    listing,
    notation,
    play_setup,
    set_hand,
    start,
)


def test_road_build_costs_cards_and_connects() -> None:
    state, _ = play_setup()
    edge = legal_free_road_edges(state, P1)[0]
    funded = action_state(set_hand(state, P1, ROAD_COST))
    transition = GAME.apply(funded, P1, PlaceRoad(edge))
    after = transition.state
    assert after.roads[edge] == P1
    assert after.hands[P1] == empty_hand()
    assert [event.kind for event in transition.events] == ["road_built"]


def test_settlement_and_city_builds() -> None:
    state = start()
    edge = 0
    roads: list[PlayerId | None] = [None] * 72
    roads[edge] = P1
    hand = hand_from(wood=1, brick=1, sheep=1, wheat=1)
    funded = action_state(
        replace(state, roads=tuple(roads), hands=(hand, empty_hand(), empty_hand()))
    )
    (settle,) = [
        action for action in listing(funded) if isinstance(action, PlaceSettlement)
    ][:1]
    settled = GAME.apply(funded, P1, settle).state
    assert settled.buildings[settle.vertex] == Building(P1, "settlement")
    assert settled.hands[P1] == empty_hand()

    city_state = action_state(set_hand(settled, P1, CITY_COST))
    city_candidates = [
        action for action in listing(city_state) if isinstance(action, BuildCity)
    ]
    (city,) = city_candidates[:1]
    built = GAME.apply(city_state, P1, city).state
    assert built.buildings[city.vertex] == Building(P1, "city")
    assert built.hands[P1] == empty_hand()


def test_no_builds_without_cards() -> None:
    state, _ = play_setup()
    broke = action_state(set_hand(state, P1, empty_hand()))
    assert [action for action in listing(broke) if isinstance(action, PlaceRoad)] == []
    assert [
        action for action in listing(broke) if isinstance(action, PlaceSettlement)
    ] == []
    assert [action for action in listing(broke) if isinstance(action, BuildCity)] == []
    assert [action for action in listing(broke) if isinstance(action, BuyDev)] == []
    assert notation(broke)[0] == "end turn"


def test_settlement_piece_limit_stops_the_listing() -> None:
    state = start()
    target = 0
    roads: list[PlayerId | None] = [None] * 72
    roads[VERTEX_EDGES[target][0]] = P1
    buildings: list[Building | None] = [None] * 54
    far = [
        vertex
        for vertex in range(54)
        if vertex != target and vertex not in VERTEX_NEIGHBORS[target]
    ][:MAX_SETTLEMENTS]
    for vertex in far:
        buildings[vertex] = Building(P1, "settlement")
    state = action_state(
        replace(state, roads=tuple(roads), buildings=tuple(buildings), active=P1)
    )
    state = set_hand(state, P1, SETTLEMENT_COST)
    assert not settlement_pieces_available(state, P1)
    assert not any(isinstance(action, PlaceSettlement) for action in listing(state))


def test_no_city_on_another_players_settlement() -> None:
    state, _ = play_setup()
    vertex = 0
    buildings: list[Building | None] = [None] * 54
    buildings[vertex] = Building(P2, "settlement")
    state = replace(state, buildings=tuple(buildings), phase="actions", dice=(1, 2))
    assert not city_legal(state, vertex, P1)
    assert BuildCity(vertex) not in listing(state)
