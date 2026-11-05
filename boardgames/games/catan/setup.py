"""Catan setup: config checks, the dealt board and the snake-order opening."""

from dataclasses import replace

from boardgames.core import (
    ConfigError,
    Event,
    PlayerId,
    Rng,
    Transition,
    seat_label,
)
from boardgames.core.records import to_json_object
from boardgames.games.catan.geometry import (
    EDGE_VERTICES,
    HEX_NEIGHBORS,
    PORT_EDGES,
    VERTEX_EDGES,
    VERTEX_HEXES,
)
from boardgames.games.catan.model import (
    DEV_DECK_COUNTS,
    NUMBER_TOKENS,
    RED_NUMBERS,
    RESOURCES,
    TERRAIN_DECK,
    TERRAIN_RESOURCE,
    Action,
    Building,
    CatanConfig,
    CatanState,
    Hand,
    Hex,
    PlaceRoad,
    PlaceSettlement,
    Port,
    Resource,
    Terrain,
    empty_dev_hand,
    empty_hand,
    hand_json,
    hand_plus,
    hand_total,
    hand_with,
    replace_at,
)
from boardgames.games.catan.rules import setup_road_legal, setup_settlement_legal


def check_config(config: CatanConfig) -> None:
    """Raise ConfigError for an unplayable table or victory target."""
    if not 3 <= config.num_players <= 4:
        raise ConfigError(f"Catan needs 3 or 4 players, got {config.num_players}")
    if not 3 <= config.victory_points <= 20:
        raise ConfigError(
            f"victory_points must be between 3 and 20, got {config.victory_points}"
        )
    if not 0 <= config.max_offers_per_turn <= 20:
        raise ConfigError(
            "max_offers_per_turn must be between 0 and 20, got "
            f"{config.max_offers_per_turn}"
        )
    return


def number_hexes(
    terrains: tuple[Terrain, ...], numbers: tuple[int, ...]
) -> tuple[Hex, ...]:
    """Hexes with tokens dealt in hex order, skipping the desert."""
    tokens = iter(numbers)
    return tuple(
        Hex(terrain, None if terrain == "desert" else next(tokens))
        for terrain in terrains
    )


def red_numbers_touch(board_hexes: tuple[Hex, ...]) -> bool:
    """Whether two neighbouring hexes both carry a 6 or an 8."""
    red = [
        hex_id
        for hex_id, board_hex in enumerate(board_hexes)
        if board_hex.number in RED_NUMBERS
    ]
    return any(neighbor in red for hex_id in red for neighbor in HEX_NEIGHBORS[hex_id])


def place_number_tokens(
    terrains: tuple[Terrain, ...], rng: Rng
) -> tuple[tuple[Hex, ...], Rng]:
    """Deal number tokens, redrawing until no two red numbers are adjacent."""
    while True:
        numbers, rng = rng.shuffled(NUMBER_TOKENS)
        board_hexes = number_hexes(terrains, numbers)
        if not red_numbers_touch(board_hexes):
            return board_hexes, rng


def setup_order(config: CatanConfig) -> tuple[PlayerId, ...]:
    """Settlement order: clockwise, then back counter-clockwise."""
    forward = tuple(PlayerId(index) for index in range(config.num_players))
    return (*forward, *reversed(forward))


def start_game(config: CatanConfig, seed: int) -> Transition[CatanState]:
    """Deal the board, ports and deck from the seed; the first seat places first."""
    rng = Rng.seeded(seed)
    terrains, rng = rng.shuffled(TERRAIN_DECK)
    board_hexes, rng = place_number_tokens(terrains, rng)

    port_kinds: tuple[Resource | None, ...] = (None, None, None, None, *RESOURCES)
    shuffled_ports, rng = rng.shuffled(port_kinds)
    ports = tuple(
        Port(edge, kind) for edge, kind in zip(PORT_EDGES, shuffled_ports, strict=True)
    )
    dev_deck, rng = rng.shuffled(DEV_DECK_COUNTS)
    robber = next(
        hex_id
        for hex_id, board_hex in enumerate(board_hexes)
        if board_hex.terrain == "desert"
    )

    player_count = config.num_players
    state = CatanState(
        config=config,
        rng=rng,
        hexes=board_hexes,
        ports=ports,
        robber=robber,
        dev_deck=dev_deck,
        turn=1,
        active=PlayerId(0),
        phase="setup_settlement",
        setup_index=0,
        setup_vertex=None,
        buildings=(None,) * len(VERTEX_HEXES),
        roads=(None,) * len(EDGE_VERTICES),
        hands=(empty_hand(),) * player_count,
        dev_hands=(empty_dev_hand(),) * player_count,
        knights_played=(0,) * player_count,
        longest_road=None,
        largest_army=None,
        dev_bought=empty_dev_hand(),
        dev_played_this_turn=False,
        free_roads=0,
        offers_this_turn=0,
        discard_remaining=(0,) * player_count,
        dice=None,
        pending_offer=None,
        winner=None,
    )
    order = setup_order(config)
    events = [
        Event(
            "started",
            f"New game: Catan for {player_count} players; first to "
            f"{config.victory_points} victory points wins.",
            to_json_object(config),
        ),
        Event(
            "board_prepared",
            f"The board is set; the robber starts on the desert h{robber}.",
            {
                "robber": robber,
                "hexes": [
                    {"terrain": board_hex.terrain, "number": board_hex.number}
                    for board_hex in board_hexes
                ],
                "ports": [
                    {"edge": port.edge, "resource": port.resource} for port in ports
                ],
            },
        ),
        Event(
            "setup_started",
            f"{seat_label(order[0])} places a settlement, then a road.",
            {"player": order[0]},
        ),
    ]
    return Transition(replace(state, active=order[0]), tuple(events))


def setup_settlement_actions(state: CatanState) -> list[Action]:
    """Every empty intersection at distance from the settlements already placed."""
    return [
        PlaceSettlement(vertex)
        for vertex in range(len(state.buildings))
        if setup_settlement_legal(state, vertex)
    ]


def setup_road_edges(state: CatanState, vertex: int) -> tuple[int, ...]:
    """Empty paths touching the settlement just placed."""
    return tuple(
        edge for edge in VERTEX_EDGES[vertex] if setup_road_legal(state, edge, vertex)
    )


def setup_road_actions(state: CatanState) -> list[Action]:
    """Roads touching the settlement just placed; none before it is placed."""
    if state.setup_vertex is None:
        return []
    return [PlaceRoad(edge) for edge in setup_road_edges(state, state.setup_vertex)]


def starting_resources(state: CatanState, vertex: int) -> Hand:
    """Resources from the hexes around a player's second settlement."""
    gains = empty_hand()
    for hex_id in VERTEX_HEXES[vertex]:
        board_hex = state.hexes[hex_id]
        resource = TERRAIN_RESOURCE[board_hex.terrain]
        if resource is None or hex_id == state.robber:
            continue
        gains = hand_with(gains, resource, 1)
    return gains


def place_setup_settlement(
    state: CatanState, player: PlayerId, vertex: int
) -> Transition[CatanState]:
    """Place an opening settlement; the second one pays starting resources."""
    building = Building(player, "settlement")
    buildings = replace_at(state.buildings, vertex, building)
    events = [
        Event(
            "settlement_built",
            f"{seat_label(player)} placed a settlement on v{vertex}.",
            {"player": player, "vertex": vertex},
        )
    ]
    new_state = replace(
        state,
        buildings=buildings,
        setup_vertex=vertex,
        phase="setup_road",
    )
    if state.setup_index >= state.config.num_players:
        gains = starting_resources(state, vertex)
        new_state = replace(
            new_state,
            hands=replace_at(
                new_state.hands, player, hand_plus(state.hands[player], gains)
            ),
        )
        if hand_total(gains):
            events.append(
                Event(
                    "starting_resources",
                    f"{seat_label(player)} received starting resources.",
                    {"player": player, "gains": hand_json(gains)},
                )
            )
    return Transition(new_state, tuple(events))


def advance_setup(state: CatanState) -> tuple[CatanState, list[Event]]:
    """Move to the next setup placement, or begin the first turn."""
    order = setup_order(state.config)
    next_index = state.setup_index + 1
    if next_index < len(order):
        next_player = order[next_index]
        return (
            replace(
                state,
                setup_index=next_index,
                active=next_player,
                phase="setup_settlement",
                setup_vertex=None,
            ),
            [
                Event(
                    "setup_turn",
                    f"{seat_label(next_player)} places a settlement, then a road.",
                    {"player": next_player},
                )
            ],
        )
    return (
        replace(
            state,
            setup_index=next_index,
            active=PlayerId(0),
            phase="roll",
            turn=1,
            setup_vertex=None,
        ),
        [
            Event(
                "setup_complete",
                f"Setup complete. {seat_label(PlayerId(0))} begins.",
                {},
            ),
            Event(
                "turn_started",
                f"{seat_label(PlayerId(0))}'s turn.",
                {"player": PlayerId(0)},
            ),
        ],
    )


def place_setup_road(
    state: CatanState, player: PlayerId, edge: int
) -> Transition[CatanState]:
    """Place an opening road, then pass the placement on in snake order."""
    roads = replace_at(state.roads, edge, player)
    events = [
        Event(
            "road_built",
            f"{seat_label(player)} placed a road on e{edge}.",
            {"player": player, "edge": edge},
        )
    ]
    advanced, next_events = advance_setup(
        replace(state, roads=roads, setup_vertex=None)
    )
    return Transition(advanced, tuple([*events, *next_events]))
