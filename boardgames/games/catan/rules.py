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
    building_counts,
    empty_hand,
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


def settlement_connected(state: CatanState, vertex: int, player: PlayerId) -> bool:
    """Whether one of the player's roads touches the intersection."""
    return any(state.roads[edge] == player for edge in VERTEX_EDGES[vertex])


def settlement_pieces_available(state: CatanState, player: PlayerId) -> bool:
    """Whether the player has an unused settlement piece."""
    settlements, _ = building_counts(state, player)
    return settlements < MAX_SETTLEMENTS


def city_legal(state: CatanState, vertex: int, player: PlayerId) -> bool:
    """Whether the player may upgrade this settlement to a city."""
    building = state.buildings[vertex]
    if building is None or building.player != player or building.kind != "settlement":
        return False
    return city_pieces_available(state, player)


def city_pieces_available(state: CatanState, player: PlayerId) -> bool:
    """Whether the player has an unused city piece."""
    _, cities = building_counts(state, player)
    return cities < MAX_CITIES


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
    """Whether a road joins the network; opponent buildings block passage."""
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
        edge for edge in range(len(state.roads)) if road_legal(state, edge, player)
    )


def robber_victims(
    state: CatanState, hex_id: int, thief: PlayerId
) -> tuple[PlayerId, ...]:
    """Opponents of `thief` with a building on `hex_id`, even with no cards."""
    victims: list[PlayerId] = []
    for player in seats(state.config.num_players):
        if player == thief:
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
    """Longest trail of the player's roads, each road at most once."""
    adjacent = road_adjacency(state, player)
    blocked = frozenset(
        vertex
        for vertex, building in enumerate(state.buildings)
        if building is not None and building.player != player
    )
    return max(
        (trail_length(vertex, adjacent, blocked, frozenset()) for vertex in adjacent),
        default=0,
    )


def road_adjacency(
    state: CatanState, player: PlayerId
) -> dict[int, list[tuple[int, int]]]:
    """(road, far end) pairs for each intersection the player's roads touch."""
    adjacent: dict[int, list[tuple[int, int]]] = {}
    for edge, (first, second) in enumerate(EDGE_VERTICES):
        if state.roads[edge] != player:
            continue
        adjacent.setdefault(first, []).append((edge, second))
        adjacent.setdefault(second, []).append((edge, first))
    return adjacent


def trail_length(
    vertex: int,
    adjacent: dict[int, list[tuple[int, int]]],
    blocked: frozenset[int],
    used: frozenset[int],
) -> int:
    """Longest trail leaving `vertex` over roads not in `used`."""
    best = 0
    for edge, next_vertex in adjacent[vertex]:
        if edge in used:
            continue
        onward = (
            0
            if next_vertex in blocked
            else trail_length(next_vertex, adjacent, blocked, used | {edge})
        )
        best = max(best, 1 + onward)
    return best


def longest_road_lengths(state: CatanState) -> tuple[int, ...]:
    """Longest road length for every seat."""
    return tuple(
        longest_road_length(state, player) for player in seats(state.config.num_players)
    )
