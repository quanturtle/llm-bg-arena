"""Static board layouts for drawn boards; the game modules own the geometry."""

from pydantic import JsonValue as PlainJson

from boardgames.games.catan import geometry


def catan_layout() -> dict[str, PlainJson]:
    """Hex centres, intersection points and paths of the standard board.

    Coordinates are the geometry module's: unit hexes with corners at distance 1
    from the centre and y growing upward.
    """
    return {
        "hexes": [
            {"id": hex_id, "x": geometry.center(q, r)[0], "y": geometry.center(q, r)[1]}
            for hex_id, (q, r) in enumerate(geometry.HEXES)
        ],
        "vertices": [
            {"id": vertex_id, "x": x, "y": y}
            for vertex_id, (x, y) in enumerate(geometry.VERTICES)
        ],
        "edges": [
            {"id": edge_id, "vertices": [first, second]}
            for edge_id, (first, second) in enumerate(geometry.EDGE_VERTICES)
        ],
        "hex_vertices": [list(ring) for ring in geometry.HEX_VERTICES],
    }


LAYOUTS = {"catan": catan_layout}


def game_layout(game_id: str) -> dict[str, PlainJson] | None:
    """The layout of a game with a drawn board, None for games rendered from data."""
    builder = LAYOUTS.get(game_id)
    return None if builder is None else builder()
