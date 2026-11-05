from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.catan import BuildCity, Building
from boardgames.games.catan.awards import (
    longest_road_holder,
    update_largest_army,
    update_longest_road,
)
from boardgames.games.catan.geometry import HEX_EDGES, HEX_VERTICES, VERTEX_EDGES
from boardgames.games.catan.model import CITY_COST
from boardgames.games.catan.rules import longest_road_length, longest_road_lengths
from tests.games.catan.support import (
    GAME,
    P1,
    P2,
    P3,
    action_state,
    path_edges,
    path_vertices,
    play_setup,
    set_hand,
    start,
)


def test_longest_road_award_and_break() -> None:
    state = start()
    path = path_edges(5)
    roads: list[PlayerId | None] = [None] * 72
    for edge in path:
        roads[edge] = P1
    built = replace(
        state,
        roads=tuple(roads),
        buildings=(None,) * 54,
        longest_road=None,
    )
    assert longest_road_length(built, P1) == 5
    awarded, events = update_longest_road(state, built)
    assert awarded.longest_road == P1
    assert any(event.kind == "longest_road" for event in events)

    vertices = path_vertices(path)
    internal = vertices[2]
    buildings = list(built.buildings)
    buildings[internal] = Building(P2, "settlement")
    broken = replace(awarded, buildings=tuple(buildings))
    assert longest_road_length(broken, P1) < 5
    assert update_longest_road(awarded, broken)[0].longest_road is None


def test_a_broken_longest_road_tied_for_first_is_set_aside() -> None:
    ring, corners = HEX_EDGES[9], HEX_VERTICES[9]
    spur = next(edge for edge in VERTEX_EDGES[corners[5]] if edge not in ring)
    buildings: list[Building | None] = [None] * 54
    buildings[corners[1]] = Building(P3, "settlement")
    for p2_roads, holder in ((5, None), (4, P1)):
        roads: list[PlayerId | None] = [None] * 72
        for edge in (spur, *ring[:5]):
            roads[edge] = P1
        for edge in HEX_EDGES[0][:p2_roads]:
            roads[edge] = P2
        held = replace(start(), roads=tuple(roads), longest_road=P1)
        broken = replace(held, buildings=tuple(buildings))
        assert longest_road_lengths(held) == (6, p2_roads, 0)
        assert longest_road_lengths(broken) == (5, p2_roads, 0)
        assert update_longest_road(held, broken)[0].longest_road == holder


def test_largest_army_keeps_ties_and_changes_on_a_strict_lead() -> None:
    state = start()
    three = replace(state, knights_played=(3, 0, 0), largest_army=None)
    awarded, _ = update_largest_army(three)
    assert awarded.largest_army == P1
    tied = replace(awarded, knights_played=(3, 3, 0))
    assert update_largest_army(tied)[0].largest_army == P1
    ahead = replace(awarded, knights_played=(3, 4, 0))
    assert update_largest_army(ahead)[0].largest_army == P2


def test_an_unbroken_longest_road_holder_keeps_a_tie() -> None:
    assert longest_road_holder((5, 5, 0), P1, is_broken=False) == P1
    assert longest_road_holder((5, 5, 0), None, is_broken=False) is None


def test_event_texts_missing_from_the_example_log() -> None:
    state, _ = play_setup()
    vertex = next(
        vertex
        for vertex, building in enumerate(state.buildings)
        if building is not None
        and building.player == P1
        and building.kind == "settlement"
    )
    state = action_state(set_hand(state, P1, CITY_COST))
    events = GAME.apply(state, P1, BuildCity(vertex)).events
    assert next(event.text for event in events if event.kind == "city_built") == (
        f"P1 upgraded v{vertex} to a city."
    )

    army = replace(start(), knights_played=(3, 4, 0), largest_army=P1)
    _, army_events = update_largest_army(army)
    assert (
        next(event.text for event in army_events if event.kind == "largest_army_lost")
        == "P1 lost the largest army."
    )

    path = path_edges(5)
    previous = replace(
        start(),
        roads=tuple(P1 if edge in path else None for edge in range(72)),
        buildings=(None,) * 54,
        longest_road=P1,
    )
    current = replace(
        previous,
        roads=tuple(P2 if edge in path else None for edge in range(72)),
    )
    _, road_events = update_longest_road(previous, current)
    assert (
        next(event.text for event in road_events if event.kind == "longest_road_lost")
        == "P1 lost the longest road."
    )
    return
