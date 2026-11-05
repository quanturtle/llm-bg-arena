"""Shared Catan test fixtures: a seeded game, scripted setup and board paths."""

from dataclasses import replace
from typing import Any

from boardgames.core import PlayerId, seats
from boardgames.games.catan import Catan, CatanConfig, CatanState
from boardgames.games.catan.geometry import EDGE_VERTICES, VERTEX_EDGES, VERTEX_HEXES
from boardgames.games.catan.model import DevHand

GAME = Catan()
CONFIG = CatanConfig(num_players=3, victory_points=5)
P1, P2, P3 = seats(3)


def start(config: CatanConfig = CONFIG, seed: int = 1) -> CatanState:
    return GAME.setup(config, seed).state


def play_setup(
    config: CatanConfig = CONFIG, seed: int = 1
) -> tuple[CatanState, list[tuple[PlayerId, Any]]]:
    """Play the setup phase choosing the first legal placement each time."""
    state = start(config, seed)
    placements: list[tuple[PlayerId, Any]] = []
    while state.phase in ("setup_settlement", "setup_road"):
        decisions = GAME.pending_decisions(state)
        assert decisions
        decision = decisions[0]
        listing = GAME.legal_actions(state, decision).listing(1_000)
        assert listing
        action = listing[0]
        placements.append((decision.player, action))
        state = GAME.apply(state, decision.player, action).state
    return state, placements


def action_state(
    state: CatanState, hands: tuple[tuple[int, ...], ...] | None = None
) -> CatanState:
    """A post-roll action state for the active player."""
    updated = replace(state, phase="actions", dice=(1, 2), pending_offer=None)
    if hands is not None:
        updated = replace(updated, hands=hands)  # type: ignore[arg-type]
    return updated


def set_hand(state: CatanState, player: PlayerId, hand: tuple[int, ...]) -> CatanState:
    """Replace one player's resource hand."""
    hands = (*state.hands[:player], hand, *state.hands[player + 1 :])
    return replace(state, hands=hands)  # type: ignore[arg-type]


def set_dev_hand(state: CatanState, player: PlayerId, hand: DevHand) -> CatanState:
    """Replace one player's development-card hand."""
    hands = (*state.dev_hands[:player], hand, *state.dev_hands[player + 1 :])
    return replace(state, dev_hands=hands)


def listing(state: CatanState) -> tuple[Any, ...]:
    (decision,) = GAME.pending_decisions(state)
    actions = GAME.legal_actions(state, decision).listing(10_000)
    assert actions is not None
    return actions


def notation(state: CatanState) -> list[str]:
    return [GAME.format_action(action) for action in listing(state)]


def path_edges(length: int) -> list[int]:
    """A simple path of `length` edges somewhere on the board."""
    for start in range(len(VERTEX_HEXES)):
        found = extend_path(start, {start}, [], length)
        if found is not None and len(found) == length:
            return found
    raise AssertionError("no path found")


def extend_path(
    vertex: int, visited: set[int], edges: list[int], length: int
) -> list[int] | None:
    if len(edges) == length:
        return list(edges)
    for edge in VERTEX_EDGES[vertex]:
        first, second = EDGE_VERTICES[edge]
        next_vertex = second if first == vertex else first
        if next_vertex in visited:
            continue
        found = extend_path(
            next_vertex, {*visited, next_vertex}, [*edges, edge], length
        )
        if found is not None:
            return found
    return None


def path_vertices(edges: list[int]) -> list[int]:
    """Vertices along a simple path of edges."""
    first, second = EDGE_VERTICES[edges[0]]
    vertices = [first, second]
    for edge in edges[1:]:
        a, b = EDGE_VERTICES[edge]
        if a == vertices[-1]:
            vertices.append(b)
        elif b == vertices[-1]:
            vertices.append(a)
        else:
            raise AssertionError("edges are not a connected path")
    return vertices
