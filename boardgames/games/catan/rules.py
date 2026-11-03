"""Pure queries over Catan state: connectivity, ports, production, longest road."""

from boardgames.core import PlayerId, seats
from boardgames.games.catan.geometry import (
    EDGE_VERTICES,
    HEX_VERTICES,
    VERTEX_EDGES,
    VERTEX_NEIGHBORS,
)
from boardgames.games.catan.model import (
    MAX_CITIES,
    MAX_ROADS,
    MAX_SETTLEMENTS,
    RESOURCES,
    TERRAIN_RESOURCE,
    CatanState,
    Hand,
    Resource,
    empty_hand,
    hand_total,
    hand_with,
    road_count,
)


def building_at(state: CatanState, vertex: int) -> PlayerId | None:
    """Owner of a building on an intersection, if any."""
    building = state.buildings[vertex]
    return None if building is None else building.player


def distance_rule_ok(state: CatanState, vertex: int) -> bool:
    """No building on `vertex` and none on an adjacent intersection."""
    if state.buildings[vertex] is not None:
        return False
    return all(
        state.buildings[neighbor] is None for neighbor in VERTEX_NEIGHBORS[vertex]
    )


def setup_settlement_legal(state: CatanState, vertex: int) -> bool:
    """An empty intersection at distance from every other settlement."""
    return 0 <= vertex < len(state.buildings) and distance_rule_ok(state, vertex)


def settlement_legal(state: CatanState, vertex: int, player: PlayerId) -> bool:
    """A connected empty intersection with a free settlement piece."""
    return (
        distance_rule_ok(state, vertex)
        and settlement_connected(state, vertex, player)
        and settlement_pieces_available(state, player)
    )


def settlement_connected(state: CatanState, vertex: int, player: PlayerId) -> bool:
    """Whether one of the player's roads touches the intersection."""
    return any(state.roads[edge] == player for edge in VERTEX_EDGES[vertex])


def settlement_pieces_available(state: CatanState, player: PlayerId) -> bool:
    """Whether the player has an unused settlement piece."""
    used = sum(
        1
        for building in state.buildings
        if building is not None
        and building.player == player
        and building.kind == "settlement"
    )
    return used < MAX_SETTLEMENTS


def city_legal(state: CatanState, vertex: int, player: PlayerId) -> bool:
    """Whether the player may upgrade this settlement to a city."""
    building = state.buildings[vertex]
    if building is None or building.player != player or building.kind != "settlement":
        return False
    return city_pieces_available(state, player)


def city_pieces_available(state: CatanState, player: PlayerId) -> bool:
    """Whether the player has an unused city piece."""
    return (
        sum(
            1
            for building in state.buildings
            if building is not None
            and building.player == player
            and building.kind == "city"
        )
        < MAX_CITIES
    )


def setup_road_legal(state: CatanState, edge: int, anchor: int) -> bool:
    """An empty path touching the settlement the player just placed."""
    return (
        0 <= edge < len(state.roads)
        and state.roads[edge] is None
        and anchor in EDGE_VERTICES[edge]
    )


def road_legal(state: CatanState, edge: int, player: PlayerId) -> bool:
    """An empty, connected path with a free road piece."""
    return (
        0 <= edge < len(state.roads)
        and state.roads[edge] is None
        and road_connected(state, edge, player)
        and road_pieces_available(state, player)
    )


def road_connected(state: CatanState, edge: int, player: PlayerId) -> bool:
    """Whether a new road on `edge` joins the player's road network.

    Another player's building blocks passage through its intersection, so a
    road ending there does not connect to roads on its far side.
    """
    for vertex in EDGE_VERTICES[edge]:
        building = state.buildings[vertex]
        if building is not None:
            if building.player == player:
                return True
            continue
        if any(
            other != edge and state.roads[other] == player
            for other in VERTEX_EDGES[vertex]
        ):
            return True
    return False


def road_pieces_available(state: CatanState, player: PlayerId) -> bool:
    """Whether the player has an unused road piece."""
    return road_count(state, player) < MAX_ROADS


def legal_free_road_edges(state: CatanState, player: PlayerId) -> tuple[int, ...]:
    """Empty paths a free road from Road Building could use."""
    return tuple(
        edge
        for edge in range(len(state.roads))
        if state.roads[edge] is None and road_legal(state, edge, player)
    )


def robber_victims(state: CatanState, hex_id: int) -> tuple[PlayerId, ...]:
    """Players with a building on `hex_id` who hold at least one card."""
    victims: list[PlayerId] = []
    for player in seats(state.config.num_players):
        if hand_total(state.hands[player]) == 0:
            continue
        if any(building_at(state, vertex) == player for vertex in HEX_VERTICES[hex_id]):
            victims.append(player)
    return tuple(victims)


def production(state: CatanState, total: int) -> tuple[Hand, ...]:
    """Resources produced by a non-seven roll, one hand per player."""
    gains = [empty_hand() for _ in seats(state.config.num_players)]
    for hex_id, board_hex in enumerate(state.hexes):
        if board_hex.number != total or hex_id == state.robber:
            continue
        resource = TERRAIN_RESOURCE[board_hex.terrain]
        if resource is None:
            continue
        for vertex in HEX_VERTICES[hex_id]:
            building = state.buildings[vertex]
            if building is None:
                continue
            amount = 1 if building.kind == "settlement" else 2
            gains[building.player] = hand_with(gains[building.player], resource, amount)
    return tuple(gains)


def trade_rates(state: CatanState, player: PlayerId) -> dict[Resource, int]:
    """Best bank rate per resource, after harbours and 3:1 ports."""
    rates: dict[Resource, int] = {resource: 4 for resource in RESOURCES}
    generic = False
    for port in state.ports:
        if not any(
            building_at(state, vertex) == player for vertex in EDGE_VERTICES[port.edge]
        ):
            continue
        if port.resource is None:
            generic = True
        else:
            rates[port.resource] = min(rates[port.resource], 2)
    if generic:
        for resource in RESOURCES:
            rates[resource] = min(rates[resource], 3)
    return rates


def longest_road_length(state: CatanState, player: PlayerId) -> int:
    """Longest continuous run of the player's roads, in paths.

    Opponents' buildings break a road, so a path may not pass through an
    intersection they occupy. With the 15-road piece limit the search is small.
    """
    adjacent: dict[int, list[tuple[int, int]]] = {
        vertex: [] for vertex in range(len(state.buildings))
    }
    for edge, (first, second) in enumerate(EDGE_VERTICES):
        if state.roads[edge] != player:
            continue
        adjacent[first].append((edge, second))
        adjacent[second].append((edge, first))
    blocked = {
        vertex
        for vertex, building in enumerate(state.buildings)
        if building is not None and building.player != player
    }
    best = 0

    def walk(
        vertex: int, used: frozenset[int], visited: frozenset[int], length: int
    ) -> None:
        nonlocal best
        best = max(best, length)
        if vertex in blocked:
            return
        for edge, next_vertex in adjacent[vertex]:
            if edge in used or next_vertex in visited:
                continue
            walk(
                next_vertex,
                used | {edge},
                visited | {next_vertex},
                length + 1,
            )

    for edge, (first, second) in enumerate(EDGE_VERTICES):
        if state.roads[edge] != player:
            continue
        walk(first, frozenset({edge}), frozenset({first}), 1)
        walk(second, frozenset({edge}), frozenset({second}), 1)
    return best


def longest_road_lengths(state: CatanState) -> tuple[int, ...]:
    """Longest road length for every seat."""
    return tuple(
        longest_road_length(state, player) for player in seats(state.config.num_players)
    )
