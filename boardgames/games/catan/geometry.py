"""Static geometry of the standard 19-hex Catan board.

Hexes, intersections and paths get ids once, at import, by sorting their
positions. Nothing here depends on a match seed: the same id always names the
same intersection or path. Terrain, number tokens and ports live in the game
state instead.
"""

import math

RADIUS = 2
SQRT3 = math.sqrt(3.0)
CORNER_ANGLES = tuple(math.radians(30 + 60 * step) for step in range(6))

# Neighbour offsets in axial coordinates, clockwise from east.
DIRECTIONS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
)


def center(q: int, r: int) -> tuple[float, float]:
    """Pixel centre of an axial-coordinate hex."""
    return (SQRT3 * (q + r / 2.0), 1.5 * r)


def point_key(x: float, y: float) -> tuple[float, float]:
    """Rounding key that folds the same corner reached from different hexes."""
    return (round(x, 6), round(y, 6))


def build_geometry() -> None:
    """Populate the module-level board tables."""
    global HEXES, HEX_ROWS, HEX_VERTICES, HEX_EDGES
    global VERTICES, VERTEX_HEXES, VERTEX_EDGES, VERTEX_NEIGHBORS
    global EDGES, EDGE_VERTICES, EDGE_HEXES
    global COASTAL_EDGES, COASTAL_EDGE_CYCLE, PORT_EDGES

    raw_hexes = [
        (q, r)
        for q in range(-RADIUS, RADIUS + 1)
        for r in range(-RADIUS, RADIUS + 1)
        if max(abs(q), abs(r), abs(q + r)) <= RADIUS
    ]
    raw_hexes.sort(key=lambda qr: (round(center(*qr)[1], 9), round(center(*qr)[0], 9)))
    HEXES = tuple(raw_hexes)
    hex_index = {qr: index for index, qr in enumerate(HEXES)}

    # Every corner reached from every hex, folded by position.
    corners: dict[tuple[float, float], list[int]] = {}
    for qr in HEXES:
        cx, cy = center(*qr)
        for angle in CORNER_ANGLES:
            key = point_key(cx + math.cos(angle), cy + math.sin(angle))
            corners.setdefault(key, []).append(hex_index[qr])

    raw_vertices = sorted(corners, key=lambda point: (point[1], point[0]))
    vertex_index = {point: index for index, point in enumerate(raw_vertices)}
    VERTICES = tuple(raw_vertices)

    hex_vertices: list[tuple[int, ...]] = []
    for qr in HEXES:
        cx, cy = center(*qr)
        ring = tuple(
            vertex_index[point_key(cx + math.cos(angle), cy + math.sin(angle))]
            for angle in CORNER_ANGLES
        )
        hex_vertices.append(ring)
    HEX_VERTICES = tuple(hex_vertices)

    vertex_hexes: list[list[int]] = [[] for _ in VERTICES]
    for hex_id, ring in enumerate(HEX_VERTICES):
        for vertex in ring:
            vertex_hexes[vertex].append(hex_id)
    VERTEX_HEXES = tuple(tuple(hexes) for hexes in vertex_hexes)

    # One entry per distinct side, in midpoint order.
    raw_edges: set[tuple[int, int]] = set()
    for ring in HEX_VERTICES:
        for step in range(6):
            first, second = ring[step], ring[(step + 1) % 6]
            pair = (min(first, second), max(first, second))
            raw_edges.add(pair)
    hex_edges: list[list[int]] = [[] for _ in HEXES]
    edge_order = sorted(
        raw_edges,
        key=lambda pair: (
            round((VERTICES[pair[0]][1] + VERTICES[pair[1]][1]) / 2, 6),
            round((VERTICES[pair[0]][0] + VERTICES[pair[1]][0]) / 2, 6),
            pair,
        ),
    )
    edge_index = {pair: index for index, pair in enumerate(edge_order)}
    for hex_id, ring in enumerate(HEX_VERTICES):
        hex_edges[hex_id] = [
            edge_index[
                (
                    min(ring[step], ring[(step + 1) % 6]),
                    max(ring[step], ring[(step + 1) % 6]),
                )
            ]
            for step in range(6)
        ]
    EDGES = tuple(edge_order)
    EDGE_VERTICES = EDGES
    HEX_EDGES = tuple(tuple(edge_ids) for edge_ids in hex_edges)

    edge_hexes: dict[int, list[int]] = {edge: [] for edge in range(len(EDGES))}
    for hex_id, edge_ids in enumerate(HEX_EDGES):
        for edge in edge_ids:
            edge_hexes[edge].append(hex_id)
    EDGE_HEXES = tuple(tuple(hexes) for hexes in edge_hexes.values())

    vertex_edges: list[list[int]] = [[] for _ in VERTICES]
    for edge, (first, second) in enumerate(EDGE_VERTICES):
        vertex_edges[first].append(edge)
        vertex_edges[second].append(edge)
    VERTEX_EDGES = tuple(tuple(edges) for edges in vertex_edges)

    neighbors: list[list[int]] = [[] for _ in VERTICES]
    for first, second in EDGE_VERTICES:
        neighbors[first].append(second)
        neighbors[second].append(first)
    VERTEX_NEIGHBORS = tuple(tuple(sorted(items)) for items in neighbors)

    COASTAL_EDGES = tuple(
        edge for edge, hexes in enumerate(EDGE_HEXES) if len(hexes) == 1
    )
    COASTAL_EDGE_CYCLE = coastal_cycle()
    # Nine ports, spread evenly around the coast. Their types are seeded in-game.
    PORT_EDGES = tuple(
        COASTAL_EDGE_CYCLE[(index * len(COASTAL_EDGE_CYCLE)) // 9] for index in range(9)
    )

    grouped: dict[float, list[int]] = {}
    for hex_id, qr in enumerate(HEXES):
        grouped.setdefault(round(center(*qr)[1], 6), []).append(hex_id)
    HEX_ROWS = tuple(
        tuple(sorted(grouped[y], key=lambda hex_id: center(*HEXES[hex_id])[0]))
        for y in sorted(grouped, reverse=True)
    )


def coastal_cycle() -> tuple[int, ...]:
    """Coastal edges in boundary order, starting from the lowest id."""
    by_vertex: dict[int, list[int]] = {}
    for edge in COASTAL_EDGES:
        first, second = EDGE_VERTICES[edge]
        by_vertex.setdefault(first, []).append(edge)
        by_vertex.setdefault(second, []).append(edge)
    start = COASTAL_EDGES[0]
    cycle: list[int] = [start]
    previous_edge = start
    current_vertex = EDGE_VERTICES[start][1]
    while True:
        candidates = [
            edge for edge in by_vertex[current_vertex] if edge != previous_edge
        ]
        if not candidates:
            break
        edge = candidates[0]
        if edge == start:
            break
        cycle.append(edge)
        first, second = EDGE_VERTICES[edge]
        current_vertex = second if first == current_vertex else first
        previous_edge = edge
    return tuple(cycle)


# Replaced by build_geometry() below; declared here so type checkers see tuples.
HEXES: tuple[tuple[int, int], ...] = ()
HEX_ROWS: tuple[tuple[int, ...], ...] = ()
HEX_VERTICES: tuple[tuple[int, ...], ...] = ()
HEX_EDGES: tuple[tuple[int, ...], ...] = ()
VERTICES: tuple[tuple[float, float], ...] = ()
VERTEX_HEXES: tuple[tuple[int, ...], ...] = ()
VERTEX_EDGES: tuple[tuple[int, ...], ...] = ()
VERTEX_NEIGHBORS: tuple[tuple[int, ...], ...] = ()
EDGES: tuple[tuple[int, int], ...] = ()
EDGE_VERTICES: tuple[tuple[int, int], ...] = ()
EDGE_HEXES: tuple[tuple[int, ...], ...] = ()
COASTAL_EDGES: tuple[int, ...] = ()
COASTAL_EDGE_CYCLE: tuple[int, ...] = ()
PORT_EDGES: tuple[int, ...] = ()

build_geometry()
