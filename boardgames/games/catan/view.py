"""Observation data, text rendering and action descriptions for Catan."""

from boardgames.core import (
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    seat_label,
    seats,
)
from boardgames.core.json_data import (
    json_bool,
    json_int,
    json_list_of,
    json_object,
    json_optional_int,
    json_str,
    list_of_values,
)
from boardgames.games.catan.geometry import (
    EDGE_HEXES,
    EDGE_VERTICES,
    HEX_ROWS,
    VERTEX_HEXES,
)
from boardgames.games.catan.model import (
    DEV_CARDS,
    RESOURCES,
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    BuyDev,
    CatanState,
    DeclineOffer,
    DevHand,
    Discard,
    EndTurn,
    MoveRobber,
    OfferTrade,
    PlaceRoad,
    PlaceSettlement,
    PlayKnight,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
    Roll,
    dev_hand_json,
    empty_dev_hand,
    hand_json,
    hand_total,
    playable_dev_hand,
    point_breakdown,
    total_points,
)
from boardgames.games.catan.notation import DEV_CARD_NOTATION
from boardgames.games.catan.rules import (
    longest_road_lengths,
    trade_rates,
)


def observe(state: CatanState, viewer: PlayerId | None) -> Observation:
    """What `viewer` may see: public board plus their own hand and secrets."""
    players = seats(state.config.num_players)
    is_over = state.phase == "game_over"
    data: dict[str, JsonValue] = {
        "turn": state.turn,
        "phase": state.phase,
        "active": state.active,
        "setup_index": state.setup_index,
        "setup_vertex": state.setup_vertex,
        "dice": None if state.dice is None else list(state.dice),
        "robber": state.robber,
        "hexes": [
            {"terrain": board_hex.terrain, "number": board_hex.number}
            for board_hex in state.hexes
        ],
        "ports": [
            {"edge": port.edge, "resource": port.resource} for port in state.ports
        ],
        "buildings": [
            None
            if building is None
            else {"player": building.player, "kind": building.kind}
            for building in state.buildings
        ],
        "roads": list(state.roads),
        "hand_sizes": [hand_total(hand) for hand in state.hands],
        "dev_counts": [hand_total(hand) for hand in state.dev_hands],
        "dev_deck_size": len(state.dev_deck),
        "knights": list(state.knights_played),
        "public_points": [
            total_points(state, player, include_hidden=False) for player in players
        ],
        "public_breakdown": [
            point_breakdown(state, player, include_hidden=False) for player in players
        ],
        "longest_road": state.longest_road,
        "longest_road_lengths": list(longest_road_lengths(state)),
        "largest_army": state.largest_army,
        "free_roads": state.free_roads,
        "offers_this_turn": state.offers_this_turn,
        "max_offers_per_turn": state.config.max_offers_per_turn,
        "dev_played_this_turn": state.dev_played_this_turn,
        "discard_remaining": list(state.discard_remaining),
        "pending_offer": offer_data(state),
        "winner": state.winner,
        "game_over": is_over,
        "final_scores": (
            [
                {
                    "player": player,
                    "points": total_points(state, player),
                    "breakdown": point_breakdown(state, player, include_hidden=True),
                }
                for player in players
            ]
            if is_over
            else None
        ),
        "revealed_hands": [hand_json(hand) for hand in state.hands]
        if is_over
        else None,
        "revealed_dev": [dev_hand_json(hand) for hand in state.dev_hands]
        if is_over
        else None,
        "you": None if viewer is None else viewer_data(state, viewer),
    }
    return Observation(viewer, data)


def viewer_data(state: CatanState, viewer: PlayerId) -> dict[str, JsonValue]:
    """The private part of an observation: hand, cards and bank rates."""
    rates = trade_rates(state, viewer)
    return {
        "seat": viewer,
        "hand": hand_json(state.hands[viewer]),
        "dev": dev_hand_json(state.dev_hands[viewer]),
        "playable_dev": dev_hand_json(playable_dev(state, viewer)),
        "points": total_points(state, viewer),
        "breakdown": point_breakdown(state, viewer, include_hidden=True),
        "trade_rates": {resource: rates[resource] for resource in RESOURCES},
    }


def playable_dev(state: CatanState, player: PlayerId) -> DevHand:
    """Development cards the player may play right now."""
    if player != state.active or state.phase != "actions" or state.dev_played_this_turn:
        return empty_dev_hand()
    return playable_dev_hand(state, player)


def offer_data(state: CatanState) -> dict[str, JsonValue] | None:
    """The open trade offer as JSON, if any."""
    offer = state.pending_offer
    if offer is None:
        return None
    return {
        "from": offer.from_player,
        "to": offer.to_player,
        "give": offer.give,
        "take": offer.take,
    }


def render_text(observation: Observation) -> str:
    """Compact board, players and private view for prompts and the CLI."""
    data = observation.data
    lines = [
        status_line(data),
        *player_lines(data),
        road_lengths_line(data),
        dev_deck_line(data),
    ]
    if observation.viewer is not None:
        lines.append(f"You are {seat_label(observation.viewer)}.")
    lines.extend(["", "Board:"])
    lines.extend(hex_lines(data))
    lines.extend(port_lines(data))
    lines.extend(vertex_lines(data))
    lines.extend(edge_lines(data))
    lines.extend(private_lines(data, observation.viewer))
    lines.extend(final_lines(data))
    lines.append("")
    lines.append(
        "Legend: forest=wood, hills=brick, pasture=sheep, fields=wheat, "
        "mountains=ore, desert=none. A path is e<id>; an intersection is v<id>. "
        "The robber blocks production on its hex."
    )
    return "\n".join(lines)


def status_line(data: JsonObject) -> str:
    """Turn, phase and any dice, discards or offer in the foreground."""
    if json_bool(data, "game_over"):
        winner = json_optional_int(data, "winner")
        return (
            f"Game over: {seat_label(PlayerId(winner))} won."
            if winner is not None
            else "Game over."
        )
    active = PlayerId(json_int(data, "active"))
    phase = json_str(data, "phase")
    turn = json_int(data, "turn")
    if phase == "setup_settlement":
        text = f"Setup, turn {turn}: {seat_label(active)} places a settlement."
    elif phase == "setup_road":
        vertex = json_optional_int(data, "setup_vertex")
        text = (
            f"Setup, turn {turn}: {seat_label(active)} places a road next to v{vertex}."
        )
    elif phase == "roll":
        text = f"Turn {turn}: {seat_label(active)} must roll the dice."
    elif phase == "discard":
        text = f"Turn {turn}: players discard after a 7."
    elif phase == "move_robber":
        text = f"Turn {turn}: {seat_label(active)} must move the robber."
    elif phase == "free_road":
        text = (
            f"Turn {turn}: {seat_label(active)} places a free road "
            f"({json_int(data, 'free_roads')} left)."
        )
    elif phase == "trade_response":
        text = f"Turn {turn}: a player must answer a trade offer."
    else:
        text = f"Turn {turn}: {seat_label(active)} may build, trade or end the turn."
    dice = data["dice"]
    if dice is not None:
        values = json_list_of({"dice": dice}, "dice", int)
        text += (
            f" Last roll: {' + '.join(str(value) for value in values)} = {sum(values)}."
        )
    return text


def player_lines(data: JsonObject) -> list[str]:
    """One public line per player: points, visible pieces, hand and cards."""
    points, breakdowns = shown_points(data)
    hand_sizes = json_list_of(data, "hand_sizes", int)
    dev_counts = json_list_of(data, "dev_counts", int)
    knights = json_list_of(data, "knights", int)
    lines = ["Players:"]
    for player, (vp, hand, dev, played, breakdown) in enumerate(
        zip(points, hand_sizes, dev_counts, knights, breakdowns, strict=True)
    ):
        pieces = breakdown_text(breakdown)
        lines.append(
            f"  {seat_label(PlayerId(player))}: {vp:g} VP ({pieces}); "
            f"hand {hand}; dev {dev}; knights played {played}."
        )
    return lines


def shown_points(data: JsonObject) -> tuple[list[float], list[JsonObject]]:
    """Points and breakdowns per player: final ones once the game is over."""
    if not json_bool(data, "game_over") or data["final_scores"] is None:
        return number_list(data, "public_points"), object_list(data, "public_breakdown")
    scores = object_list(data, "final_scores")
    return (
        [json_number(score, "points") for score in scores],
        [json_object(score, "breakdown") for score in scores],
    )


def road_lengths_line(data: JsonObject) -> str:
    """Longest road length per player, and who holds the award."""
    lengths = json_list_of(data, "longest_road_lengths", int)
    parts = ", ".join(
        f"{seat_label(PlayerId(player))} {length}"
        for player, length in enumerate(lengths)
    )
    holder = json_optional_int(data, "longest_road")
    award = "none" if holder is None else seat_label(PlayerId(holder))
    return f"Road lengths: {parts}. Longest road award: {award}."


def dev_deck_line(data: JsonObject) -> str:
    """Development cards left to buy."""
    return f"Development deck: {json_int(data, 'dev_deck_size')} cards left."


def breakdown_text(breakdown: JsonObject) -> str:
    """Short source list such as "settlements 2, cities 2"."""
    parts: list[str] = []
    for key in (
        "settlements",
        "cities",
        "victory cards",
        "longest road",
        "largest army",
    ):
        value = breakdown.get(key, 0)
        if isinstance(value, int | float) and value:
            parts.append(f"{key} {value:g}")
    return ", ".join(parts) or "no points"


def hex_lines(data: JsonObject) -> list[str]:
    """Hexes row by row, with terrain, number and the robber marker."""
    hexes = object_list(data, "hexes")
    robber = json_int(data, "robber")
    lines = ["  Hexes:"]
    for row in HEX_ROWS:
        parts = []
        for hex_id in row:
            board_hex = hexes[hex_id]
            number = json_optional_int(board_hex, "number")
            shown = "-" if number is None else str(number)
            label = f"h{hex_id} {json_str(board_hex, 'terrain')} {shown}"
            if hex_id == robber:
                label += " [robber]"
            parts.append(label)
        lines.append("    " + " | ".join(parts))
    return lines


def port_lines(data: JsonObject) -> list[str]:
    """Harbours and their endpoints."""
    ports = object_list(data, "ports")
    parts = []
    for port in ports:
        edge = json_int(port, "edge")
        resource = port["resource"]
        kind = "3:1" if resource is None else f"2:1 {json_str(port, 'resource')}"
        first, second = EDGE_VERTICES[edge]
        parts.append(f"e{edge} {kind} (v{first}-v{second})")
    return ["  Ports: " + "; ".join(parts)]


def vertex_lines(data: JsonObject) -> list[str]:
    """Every intersection with its adjacent hexes, building and harbour."""
    buildings = optional_object_list(data, "buildings")
    ports_by_vertex = port_vertex_map(data)
    board_hexes = object_list(data, "hexes")
    lines = ["  Intersections:"]
    for vertex, hexes in enumerate(VERTEX_HEXES):
        terrains = ", ".join(hex_label(board_hexes, hex_id) for hex_id in hexes)
        building = buildings[vertex]
        occupancy = "empty" if building is None else building_text(building)
        port = ports_by_vertex.get(vertex)
        suffix = f" | port {port}" if port is not None else ""
        lines.append(f"    v{vertex}: {terrains} | {occupancy}{suffix}")
    return lines


def edge_lines(data: JsonObject) -> list[str]:
    """Every path with endpoints, adjacent hexes and road owner."""
    roads = optional_int_list(data, "roads")
    hexes = object_list(data, "hexes")
    ports = {json_int(port, "edge") for port in object_list(data, "ports")}
    lines = ["  Paths:"]
    for edge, (first, second) in enumerate(EDGE_VERTICES):
        terrains = ", ".join(hex_label(hexes, hex_id) for hex_id in EDGE_HEXES[edge])
        owner = roads[edge]
        occupancy = "empty" if owner is None else f"{seat_label(PlayerId(owner))} road"
        port = " | port" if edge in ports else ""
        lines.append(
            f"    e{edge}: v{first}-v{second} ({terrains}) | {occupancy}{port}"
        )
    return lines


def hex_label(hexes: list[JsonObject], hex_id: int) -> str:
    """Short "h3 forest 6" label."""
    board_hex = hexes[hex_id]
    number = json_optional_int(board_hex, "number")
    return (
        f"h{hex_id} {json_str(board_hex, 'terrain')} "
        f"{number if number is not None else '-'}"
    )


def building_text(building: JsonObject) -> str:
    """ "P1 settlement" for a building object."""
    player = PlayerId(json_int(building, "player"))
    return f"{seat_label(player)} {json_str(building, 'kind')}"


def port_vertex_map(data: JsonObject) -> dict[int, str]:
    """Port label keyed by each endpoint intersection."""
    result: dict[int, str] = {}
    for port in object_list(data, "ports"):
        edge = json_int(port, "edge")
        resource = port["resource"]
        label = "3:1" if resource is None else f"2:1 {json_str(port, 'resource')}"
        for vertex in EDGE_VERTICES[edge]:
            result[vertex] = label
    return result


def private_lines(data: JsonObject, viewer: PlayerId | None) -> list[str]:
    """The viewer's hand, dev cards, rates and any obligation."""
    lines: list[str] = []
    pending = data["pending_offer"]
    if pending is not None:
        lines.append(offer_line(json_object({"offer": pending}, "offer")))
    remaining = json_list_of(data, "discard_remaining", int)
    owed = [
        f"{seat_label(PlayerId(player))} {count}"
        for player, count in enumerate(remaining)
        if count
    ]
    if owed:
        lines.append("Discards still owed: " + ", ".join(owed) + ".")
    if json_int(data, "free_roads"):
        lines.append(f"Free roads left this turn: {json_int(data, 'free_roads')}.")
    max_offers = json_int(data, "max_offers_per_turn")
    if max_offers and viewer == json_int(data, "active"):
        lines.append(
            f"Trade offers this turn: {json_int(data, 'offers_this_turn')} "
            f"of {max_offers}."
        )
    if json_bool(data, "dev_played_this_turn"):
        lines.append("A development card was already played this turn.")
    if viewer is None:
        return lines
    you = json_object(data, "you")
    lines.append(
        "Your hand: "
        + hand_text(json_object(you, "hand"))
        + f" ({total(you, 'hand')} cards)."
    )
    lines.append("Your development cards: " + dev_text(json_object(you, "dev")) + ".")
    lines.append(
        "Playable development cards now: "
        + dev_text(json_object(you, "playable_dev"))
        + "."
    )
    rates = json_object(you, "trade_rates")
    lines.append(
        "Your bank rates: "
        + ", ".join(
            f"{resource} {json_int(rates, resource)}:1" for resource in RESOURCES
        )
        + "."
    )
    lines.append(
        f"Your victory points: {json_number(you, 'points'):g} "
        f"({breakdown_text(json_object(you, 'breakdown'))})."
    )
    if json_bool(data, "game_over"):
        lines.append("The game is over; all hands and development cards are revealed.")
    return lines


def final_lines(data: JsonObject) -> list[str]:
    """Final scores and revealed cards once the game is over."""
    if not json_bool(data, "game_over") or data["final_scores"] is None:
        return []
    lines = ["Final scores:"]
    for score in object_list(data, "final_scores"):
        player = PlayerId(json_int(score, "player"))
        points = json_number(score, "points")
        breakdown = json_object(score, "breakdown")
        lines.append(
            f"  {seat_label(player)}: {points:g} points ({breakdown_text(breakdown)})."
        )
    lines.extend(revealed_lines(data))
    return lines


def revealed_lines(data: JsonObject) -> list[str]:
    """Every player's hand and development cards, when the observation reveals them."""
    if data["revealed_hands"] is None or data["revealed_dev"] is None:
        return []
    hands = object_list(data, "revealed_hands")
    devs = object_list(data, "revealed_dev")
    lines = ["Revealed hands:"]
    for player, (hand, dev) in enumerate(zip(hands, devs, strict=True)):
        lines.append(
            f"  {seat_label(PlayerId(player))}: {hand_text(hand)}; "
            f"development cards: {dev_text(dev)}."
        )
    return lines


def offer_line(offer: JsonObject) -> str:
    """ "P1 offers P2 1 wood for 1 ore." """
    giver = seat_label(PlayerId(json_int(offer, "from")))
    taker = seat_label(PlayerId(json_int(offer, "to")))
    return (
        f"Open offer: {giver} offers {taker} 1 {json_str(offer, 'give')} "
        f"for 1 {json_str(offer, 'take')}."
    )


def hand_text(hand: JsonObject) -> str:
    """ "wood 2, brick 0, ..." for one resource hand."""
    return ", ".join(f"{resource} {json_int(hand, resource)}" for resource in RESOURCES)


def dev_text(hand: JsonObject) -> str:
    """ "knight 1, roadbuilding 0, ..." for one development-card hand."""
    return ", ".join(
        f"{DEV_CARD_NOTATION[card]} {json_int(hand, card)}" for card in DEV_CARDS
    )


def total(outer: JsonObject, key: str) -> int:
    """Total cards in a nested hand object."""
    hand = json_object(outer, key)
    return sum(json_int(hand, resource) for resource in RESOURCES)


def describe_action(observation: Observation, action: Action) -> str:
    """One-line description from the deciding player's view."""
    data = observation.data
    hexes = object_list(data, "hexes")
    match action:
        case Roll():
            return "Roll the two dice"
        case EndTurn():
            return "End your turn"
        case PlaceSettlement(vertex=vertex):
            return f"Place a settlement on v{vertex} ({vertex_hexes(hexes, vertex)})"
        case PlaceRoad(edge=edge):
            return f"Place a road on e{edge} ({edge_hexes(hexes, edge)})"
        case BuildCity(vertex=vertex):
            return f"Upgrade your settlement on v{vertex} to a city"
        case BuyDev():
            return "Buy a development card (1 sheep, 1 wheat, 1 ore)"
        case Discard(resource=resource):
            return f"Discard 1 {resource}"
        case MoveRobber(hex=hex_id, victim=victim):
            return robber_description("Move the robber", hexes, hex_id, victim)
        case PlayKnight(hex=hex_id, victim=victim):
            return robber_description(
                "Play a knight and move the robber", hexes, hex_id, victim
            )
        case BankTrade(give=give, give_count=count, take=take):
            return f"Trade {count} {give} to the bank for 1 {take}"
        case OfferTrade(give=give, take=take, target=target):
            return f"Offer {seat_label(target)} 1 {give} for 1 {take}"
        case AcceptOffer():
            return accept_description(data)
        case DeclineOffer():
            return "Decline the open trade offer"
        case PlayRoadBuilding():
            return "Play roadbuilding: place two free roads"
        case PlayYearOfPlenty(first=first, second=second):
            return f"Play yearofplenty: take 1 {first} and 1 {second}"
        case PlayMonopoly(resource=resource):
            return f"Play monopoly: take all {resource} from the other players"
    raise TypeError(f"unknown Catan action {action!r}")


def vertex_hexes(hexes: list[JsonObject], vertex: int) -> str:
    """ "h3 forest 6, h4 pasture 8" for an intersection."""
    return ", ".join(hex_label(hexes, hex_id) for hex_id in VERTEX_HEXES[vertex])


def edge_hexes(hexes: list[JsonObject], edge: int) -> str:
    """ "v3-v4; h2 hills 10, h3 forest 5" for a path."""
    first, second = EDGE_VERTICES[edge]
    terrains = ", ".join(hex_label(hexes, hex_id) for hex_id in EDGE_HEXES[edge])
    return f"v{first}-v{second}; {terrains}"


def robber_description(
    prefix: str, hexes: list[JsonObject], hex_id: int, victim: PlayerId | None
) -> str:
    """Robber move with the hex label and optional victim."""
    text = f"{prefix} to {hex_label(hexes, hex_id)}"
    if victim is not None:
        text += f" and steal from {seat_label(victim)}"
    return text


def accept_description(data: JsonObject) -> str:
    """Accept the pending offer, naming what each side gives."""
    pending = data["pending_offer"]
    if pending is None:
        return "Accept the open trade offer"
    offer = json_object({"offer": pending}, "offer")
    give = json_str(offer, "give")
    take = json_str(offer, "take")
    return f"Accept: give 1 {take}, receive 1 {give}"


def object_list(data: JsonObject, key: str) -> list[JsonObject]:
    """A list of JSON objects."""
    return [
        json_object({"item": item}, "item") for item in list_of_values(key, data[key])
    ]


def optional_object_list(data: JsonObject, key: str) -> list[JsonObject | None]:
    """A list of JSON objects or nulls."""
    return [
        None if item is None else json_object({"item": item}, "item")
        for item in list_of_values(key, data[key])
    ]


def optional_int_list(data: JsonObject, key: str) -> list[int | None]:
    """A list of ints or nulls."""
    return [
        None if item is None else json_int({"item": item}, "item")
        for item in list_of_values(key, data[key])
    ]


def number_list(data: JsonObject, key: str) -> list[float]:
    """A list of JSON numbers, as floats."""
    return [number_of(key, item) for item in list_of_values(key, data[key])]


def json_number(data: JsonObject, key: str) -> float:
    """One JSON number, as a float."""
    return number_of(key, data[key])


def number_of(key: str, value: JsonValue) -> float:
    """Narrow a JSON value to a number, rejecting bools."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key!r} is {value!r}, expected a number")
    return float(value)
