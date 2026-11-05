from boardgames.games.catan.geometry import (
    COASTAL_EDGES,
    EDGE_HEXES,
    EDGE_VERTICES,
    HEX_VERTICES,
    HEXES,
    PORT_EDGES,
    VERTEX_HEXES,
)


def test_board_geometry_is_standard() -> None:
    assert len(HEXES) == 19
    assert len(VERTEX_HEXES) == 54
    assert len(EDGE_VERTICES) == 72
    assert len(COASTAL_EDGES) == 30
    assert len(PORT_EDGES) == 9
    assert set(len(hexes) for hexes in EDGE_HEXES) == {1, 2}
    assert set(len(hexes) for hexes in VERTEX_HEXES) == {1, 2, 3}
    assert all(len(HEX_VERTICES[hex_id]) == 6 for hex_id in range(19))
