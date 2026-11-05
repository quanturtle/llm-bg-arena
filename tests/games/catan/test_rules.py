from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.catan import Building, Port
from boardgames.games.catan.geometry import (
    EDGE_HEXES,
    EDGE_VERTICES,
    HEX_EDGES,
    HEX_VERTICES,
    VERTEX_EDGES,
)
from boardgames.games.catan.model import MAX_CITIES, empty_hand, hand_from
from boardgames.games.catan.rules import (
    city_legal,
    longest_road_length,
    production,
    road_connected,
    robber_victims,
    trade_rates,
)
from tests.games.catan.support import P1, P2, P3, play_setup, start


def test_production_counts_settlements_and_cities_but_not_the_robber() -> None:
    state = start()
    board = [
        replace(board_hex, terrain="desert", number=None) for board_hex in state.hexes
    ]
    board[0] = replace(board[0], terrain="forest", number=6)
    board[1] = replace(board[1], terrain="pasture", number=8)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[0][0]] = Building(P1, "settlement")
    buildings[HEX_VERTICES[0][1]] = Building(P1, "city")
    controlled = replace(
        state,
        hexes=tuple(board),
        buildings=tuple(buildings),
        robber=18,
        hands=(empty_hand(),) * 3,
    )
    gains = production(controlled, 6)
    assert gains[P1] == hand_from(wood=3)
    assert gains[P2] == empty_hand()
    blocked = replace(controlled, robber=0)
    assert production(blocked, 6)[P1] == empty_hand()


def test_ports_give_three_to_one_and_two_to_one_rates() -> None:
    state, _ = play_setup()
    edge = state.ports[0].edge
    vertex = EDGE_VERTICES[edge][0]
    buildings = list(state.buildings)
    buildings[vertex] = Building(P1, "settlement")
    generic = replace(
        state,
        ports=(Port(edge, None),),
        buildings=tuple(buildings),
    )
    assert trade_rates(generic, P1)["wood"] == 3
    specific = replace(state, ports=(Port(edge, "wood"),), buildings=tuple(buildings))
    assert trade_rates(specific, P1)["wood"] == 2
    assert trade_rates(specific, P1)["ore"] == 4


def test_longest_road_is_a_trail_through_both_rings_of_a_theta() -> None:
    first, second = next(hexes for hexes in EDGE_HEXES if len(hexes) == 2)
    roads: list[PlayerId | None] = [None] * 72
    for edge in (*HEX_EDGES[first], *HEX_EDGES[second]):
        roads[edge] = P1
    theta = replace(start(), roads=tuple(roads))
    assert roads.count(P1) == 11
    assert longest_road_length(theta, P1) == 11


def test_robber_lists_opponents_even_with_empty_hands() -> None:
    state = start()
    hex_id = next(hex_id for hex_id in range(19) if hex_id != state.robber)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[hex_id][0]] = Building(P2, "settlement")
    buildings[HEX_VERTICES[hex_id][1]] = Building(P3, "settlement")
    state = replace(
        state,
        buildings=tuple(buildings),
        hands=(empty_hand(), empty_hand(), hand_from(wood=1)),
    )
    assert robber_victims(state, hex_id, P1) == (P2, P3)


def test_a_road_does_not_connect_through_an_opponent_building() -> None:
    state = start()
    vertex = 0
    edge, far_edge = VERTEX_EDGES[vertex][:2]
    roads: list[PlayerId | None] = [None] * 72
    roads[far_edge] = P1
    buildings: list[Building | None] = [None] * 54
    buildings[vertex] = Building(P2, "settlement")
    blocked = replace(state, buildings=tuple(buildings), roads=tuple(roads))
    assert not road_connected(blocked, edge, P1)
    open_state = replace(blocked, buildings=(None,) * 54)
    assert road_connected(open_state, edge, P1)


def test_city_piece_limit_stops_the_listing() -> None:
    state = start()
    buildings: list[Building | None] = [None] * 54
    for vertex in range(MAX_CITIES):
        buildings[vertex] = Building(P1, "city")
    buildings[MAX_CITIES] = Building(P1, "settlement")
    state = replace(state, buildings=tuple(buildings))
    assert not city_legal(state, MAX_CITIES, P1)


def test_harbour_needs_your_own_building() -> None:
    state, _ = play_setup()
    edge = state.ports[0].edge
    no_building = replace(state, ports=(Port(edge, None),), buildings=(None,) * 54)
    assert trade_rates(no_building, P1)["wood"] == 4
    buildings: list[Building | None] = [None] * 54
    buildings[EDGE_VERTICES[edge][0]] = Building(P2, "settlement")
    opponent = replace(no_building, buildings=tuple(buildings))
    assert trade_rates(opponent, P1)["wood"] == 4
    buildings[EDGE_VERTICES[edge][0]] = Building(P1, "settlement")
    owned = replace(no_building, buildings=tuple(buildings))
    assert trade_rates(owned, P1)["wood"] == 3
