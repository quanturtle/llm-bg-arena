"""Catan building: roads, settlements and cities, bought or placed free."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.catan.awards import finish_if_won, update_longest_road
from boardgames.games.catan.model import (
    CITY_COST,
    RESOURCES,
    ROAD_COST,
    SETTLEMENT_COST,
    Action,
    BuildCity,
    Building,
    CatanState,
    Hand,
    PlaceRoad,
    PlaceSettlement,
    can_afford,
    hand_minus,
    replace_at,
)
from boardgames.games.catan.rules import (
    city_legal,
    distance_rule_ok,
    legal_free_road_edges,
    road_legal,
    settlement_connected,
    settlement_pieces_available,
    setup_road_legal,
)


def missing_text(hand: Hand, cost: Hand) -> str:
    """ "2 wood, 1 ore" for the cards a hand lacks toward a cost."""
    parts = [
        f"{need - have} {resource}"
        for resource, have, need in zip(RESOURCES, hand, cost, strict=True)
        if have < need
    ]
    return ", ".join(parts) or "nothing"


def settlement_reason(state: CatanState, player: PlayerId, vertex: int) -> str | None:
    """Why a settlement cannot go on `vertex`; setup checks only the board."""
    if not 0 <= vertex < len(state.buildings):
        return f"v{vertex} is not on the board."
    building = state.buildings[vertex]
    if building is not None:
        return f"v{vertex} already has a {building.kind}."
    if not distance_rule_ok(state, vertex):
        return f"v{vertex} is adjacent to another building."
    if state.phase == "setup_settlement":
        return None
    if not settlement_connected(state, vertex, player):
        return f"A settlement on v{vertex} must touch one of your roads."
    if not settlement_pieces_available(state, player):
        return "You have no settlement pieces left."
    hand = state.hands[player]
    if not can_afford(hand, SETTLEMENT_COST):
        return f"You lack {missing_text(hand, SETTLEMENT_COST)} for a settlement."
    return None


def road_reason(state: CatanState, player: PlayerId, edge: int) -> str | None:
    """Why a road cannot go on `edge`; only the action phase charges for it."""
    if not 0 <= edge < len(state.roads):
        return f"e{edge} is not on the board."
    if state.roads[edge] is not None:
        return f"e{edge} already has a road."
    if state.phase == "setup_road":
        if state.setup_vertex is None:
            return "Place a settlement first."
        if not setup_road_legal(state, edge, state.setup_vertex):
            return f"Your setup road must touch v{state.setup_vertex}."
        return None
    if not road_legal(state, edge, player):
        return f"e{edge} does not connect to your network or you have no roads left."
    hand = state.hands[player]
    if state.phase == "actions" and not can_afford(hand, ROAD_COST):
        return f"You lack {missing_text(hand, ROAD_COST)} for a road."
    return None


def city_reason(state: CatanState, player: PlayerId, vertex: int) -> str | None:
    """Why `vertex` cannot be upgraded to a city."""
    if not 0 <= vertex < len(state.buildings):
        return f"v{vertex} is not on the board."
    building = state.buildings[vertex]
    if building is None:
        return f"v{vertex} has no settlement to upgrade."
    if building.player != player:
        return f"v{vertex} belongs to {seat_label(building.player)}."
    if building.kind == "city":
        return f"v{vertex} is already a city."
    if not city_legal(state, vertex, player):
        return "You have no city pieces left."
    hand = state.hands[player]
    if not can_afford(hand, CITY_COST):
        return f"You lack {missing_text(hand, CITY_COST)} for a city."
    return None


def build_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Roads, settlements and cities whose reason is None, in that order."""
    actions: list[Action] = []
    for edge in range(len(state.roads)):
        if road_reason(state, player, edge) is None:
            actions.append(PlaceRoad(edge))
    for vertex in range(len(state.buildings)):
        if settlement_reason(state, player, vertex) is None:
            actions.append(PlaceSettlement(vertex))
    for vertex in range(len(state.buildings)):
        if city_reason(state, player, vertex) is None:
            actions.append(BuildCity(vertex))
    return actions


def pay_cost(state: CatanState, player: PlayerId, cost: Hand) -> CatanState:
    """Subtract a cost from a player's hand or raise."""
    hand = hand_minus(state.hands[player], cost)
    if hand is None:
        raise IllegalActionError("you do not have the cards for that build")
    return replace(state, hands=replace_at(state.hands, player, hand))


def build_road(
    state: CatanState, player: PlayerId, edge: int
) -> Transition[CatanState]:
    """Pay for a road and place it; the longest road award may change hands."""
    paid = pay_cost(state, player, ROAD_COST)
    roads = replace_at(paid.roads, edge, player)
    events = [
        Event(
            "road_built",
            f"{seat_label(player)} built a road on e{edge}.",
            {"player": player, "edge": edge},
        )
    ]
    built, award_events = update_longest_road(state, replace(paid, roads=roads))
    events.extend(award_events)
    return finish_if_won(built, tuple(events))


def build_settlement(
    state: CatanState, player: PlayerId, vertex: int
) -> Transition[CatanState]:
    """Pay for a settlement and place it; it may break another player's road."""
    paid = pay_cost(state, player, SETTLEMENT_COST)
    buildings = replace_at(paid.buildings, vertex, Building(player, "settlement"))
    events = [
        Event(
            "settlement_built",
            f"{seat_label(player)} built a settlement on v{vertex}.",
            {"player": player, "vertex": vertex},
        )
    ]
    built, award_events = update_longest_road(state, replace(paid, buildings=buildings))
    events.extend(award_events)
    return finish_if_won(built, tuple(events))


def build_city(
    state: CatanState, player: PlayerId, vertex: int
) -> Transition[CatanState]:
    """Pay for a city and upgrade the player's settlement."""
    paid = pay_cost(state, player, CITY_COST)
    buildings = replace_at(paid.buildings, vertex, Building(player, "city"))
    events = [
        Event(
            "city_built",
            f"{seat_label(player)} upgraded v{vertex} to a city.",
            {"player": player, "vertex": vertex},
        )
    ]
    return finish_if_won(replace(paid, buildings=buildings), tuple(events))


def free_road_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Paths whose reason is None, for the next free road from Road Building."""
    return [
        PlaceRoad(edge)
        for edge in range(len(state.roads))
        if road_reason(state, player, edge) is None
    ]


def place_free_road(
    state: CatanState, player: PlayerId, edge: int
) -> Transition[CatanState]:
    """Place a free road; Road Building ends when none is left or none fits."""
    roads = replace_at(state.roads, edge, player)
    free_roads = state.free_roads - 1
    events = [
        Event(
            "road_built",
            f"{seat_label(player)} placed a free road on e{edge}.",
            {"player": player, "edge": edge, "free": True},
        )
    ]
    built = replace(state, roads=roads, free_roads=free_roads)
    built, award_events = update_longest_road(state, built)
    events.extend(award_events)
    finished = finish_if_won(built, tuple(events))
    if finished.state.phase == "game_over":
        return finished
    if free_roads > 0 and legal_free_road_edges(finished.state, player):
        return Transition(replace(finished.state, phase="free_road"), finished.events)
    exhausted = (
        Event(
            "free_roads_exhausted",
            "No more free roads can be placed.",
            {"player": player},
        )
        if free_roads > 0
        else None
    )
    return Transition(
        replace(finished.state, phase="actions", free_roads=0),
        (*finished.events, *((exhausted,) if exhausted is not None else ())),
    )
