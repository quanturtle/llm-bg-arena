import asyncio
from collections import Counter
from dataclasses import replace
from typing import Any

import pytest

from boardgames.arena.runner import play_match
from boardgames.core import (
    ConfigError,
    IllegalActionError,
    JsonObject,
    NotationError,
    PlayerId,
    Rng,
    create_game,
    seats,
)
from boardgames.core.json_data import json_object, list_of_values
from boardgames.games.catan import (
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    Building,
    BuyDev,
    Catan,
    CatanConfig,
    CatanState,
    DeclineOffer,
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
    Port,
    Roll,
)
from boardgames.games.catan.game import (
    longest_road_holder,
    setup_order,
    update_largest_army,
    update_longest_road,
)
from boardgames.games.catan.geometry import (
    COASTAL_EDGES,
    EDGE_HEXES,
    EDGE_VERTICES,
    HEX_EDGES,
    HEX_NEIGHBORS,
    HEX_VERTICES,
    HEXES,
    PORT_EDGES,
    VERTEX_EDGES,
    VERTEX_HEXES,
    VERTEX_NEIGHBORS,
)
from boardgames.games.catan.model import (
    CITY_COST,
    DEV_COST,
    MAX_CITIES,
    MAX_ROADS,
    MAX_SETTLEMENTS,
    NUMBER_TOKENS,
    RESOURCES,
    ROAD_COST,
    SETTLEMENT_COST,
    TERRAIN_RESOURCE,
    DevHand,
    dev_hand_from,
    dev_with,
    empty_dev_hand,
    empty_hand,
    hand_from,
    hand_total,
    hand_with,
)
from boardgames.games.catan.rules import (
    building_at,
    city_legal,
    legal_free_road_edges,
    longest_road_length,
    longest_road_lengths,
    production,
    road_connected,
    robber_victims,
    settlement_pieces_available,
    trade_rates,
)
from boardgames.logs.replay import replay_match
from boardgames.logs.schema import LogRecord
from tests.arena.support import FakeClock, MemorySink, random_agents
from tests.invariants.playthrough import random_playthrough

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


def record_match(config: CatanConfig, seed: int) -> list[LogRecord]:
    sink = MemorySink()
    asyncio.run(
        play_match(
            GAME,
            config,
            seed,
            random_agents(config.num_players, seed),
            match_id="catan-test",
            sink=sink,
            clock=FakeClock(),
        )
    )
    return sink.records


def test_board_geometry_is_standard() -> None:
    assert len(HEXES) == 19
    assert len(VERTEX_HEXES) == 54
    assert len(EDGE_VERTICES) == 72
    assert len(COASTAL_EDGES) == 30
    assert len(PORT_EDGES) == 9
    assert set(len(hexes) for hexes in EDGE_HEXES) == {1, 2}
    assert set(len(hexes) for hexes in VERTEX_HEXES) == {1, 2, 3}
    assert all(len(HEX_VERTICES[hex_id]) == 6 for hex_id in range(19))


def test_setup_prepares_a_seeded_board() -> None:
    state = start()
    terrains = Counter(board_hex.terrain for board_hex in state.hexes)
    assert terrains == {
        "forest": 4,
        "pasture": 4,
        "fields": 4,
        "hills": 3,
        "mountains": 3,
        "desert": 1,
    }
    numbers = sorted(
        board_hex.number for board_hex in state.hexes if board_hex.number is not None
    )
    assert tuple(numbers) == tuple(sorted(NUMBER_TOKENS))
    assert state.hexes[state.robber].terrain == "desert"
    assert len(state.ports) == 9
    assert sum(1 for port in state.ports if port.resource is None) == 4
    assert sorted(
        port.resource for port in state.ports if port.resource is not None
    ) == sorted(RESOURCES)
    assert all(building is None for building in state.buildings)
    assert all(owner is None for owner in state.roads)
    assert all(hand_total(hand) == 0 for hand in state.hands)
    assert state.phase == "setup_settlement"
    assert state.turn == 1


def test_six_and_eight_tokens_never_touch() -> None:
    for seed in range(50):
        hexes = start(seed=seed).hexes
        red = [hex_id for hex_id, board in enumerate(hexes) if board.number in (6, 8)]
        assert len(red) == 4
        assert not any(
            other in red for hex_id in red for other in HEX_NEIGHBORS[hex_id]
        )


def test_setup_is_deterministic_per_seed() -> None:
    assert start(seed=9) == start(seed=9)
    assert GAME.setup(CONFIG, 9).events == GAME.setup(CONFIG, 9).events
    assert start(seed=9) != start(seed=10)


def test_setup_turn_order_snakes_back() -> None:
    state = start()
    order = setup_order(CONFIG)
    assert [state.active] == [order[0]]
    state, placements = play_setup()
    players = [player for player, _ in placements]
    expected = [player for player in order for _ in range(2)]
    assert players == expected
    assert state.phase == "roll"
    assert state.active == P1
    assert state.turn == 1
    for player in seats(3):
        settlements = sum(
            1
            for building in state.buildings
            if building is not None
            and building.player == player
            and building.kind == "settlement"
        )
        roads = sum(1 for owner in state.roads if owner == player)
        assert settlements == 2
        assert roads == 2


def test_second_settlement_grants_starting_resources() -> None:
    state, placements = play_setup()
    second: dict[int, int] = {}
    for player, action in placements:
        if isinstance(action, PlaceSettlement):
            if player in second:
                second[player] = action.vertex
            else:
                second[player] = -1
    for player in seats(3):
        expected = empty_hand()
        for hex_id in VERTEX_HEXES[second[player]]:
            board_hex = state.hexes[hex_id]
            resource = TERRAIN_RESOURCE[board_hex.terrain]
            if resource is not None and hex_id != state.robber:
                expected = hand_with(expected, resource, 1)
        assert state.hands[player] == expected


def test_first_settlement_grants_nothing() -> None:
    state = start()
    decision = GAME.pending_decisions(state)[0]
    action = GAME.legal_actions(state, decision).listing(1000)[0]  # type: ignore[index]
    after = GAME.apply(state, decision.player, action).state
    assert hand_total(after.hands[decision.player]) == 0
    assert after.phase == "setup_road"
    assert after.setup_vertex is not None


def test_production_counts_settlements_and_cities_but_not_the_robber() -> None:
    state = start()
    board = [
        replace(board_hex, terrain="desert", number=None) for board_hex in state.hexes
    ]
    board[0] = replace(board[0], terrain="forest", number=6)
    board[1] = replace(board[1], terrain="pasture", number=8)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[0][0]] = Building(P1, "settlement")
    buildings[HEX_VERTICES[0][1]] = Building(P1, "city")
    controlled = replace(
        state,
        hexes=tuple(board),
        buildings=tuple(buildings),
        robber=18,
        hands=(empty_hand(),) * 3,
    )
    gains = production(controlled, 6)
    assert gains[P1] == hand_from(wood=3)
    assert gains[P2] == empty_hand()
    blocked = replace(controlled, robber=0)
    assert production(blocked, 6)[P1] == empty_hand()


def test_road_build_costs_cards_and_connects() -> None:
    state, _ = play_setup()
    edge = legal_free_road_edges(state, P1)[0]
    funded = action_state(set_hand(state, P1, ROAD_COST))
    transition = GAME.apply(funded, P1, PlaceRoad(edge))
    after = transition.state
    assert after.roads[edge] == P1
    assert after.hands[P1] == empty_hand()
    assert [event.kind for event in transition.events] == ["road_built"]


def test_settlement_and_city_builds() -> None:
    state = start()
    edge = 0
    roads: list[PlayerId | None] = [None] * 72
    roads[edge] = P1
    hand = hand_from(wood=1, brick=1, sheep=1, wheat=1)
    funded = action_state(
        replace(state, roads=tuple(roads), hands=(hand, empty_hand(), empty_hand()))
    )
    (settle,) = [
        action for action in listing(funded) if isinstance(action, PlaceSettlement)
    ][:1]
    settled = GAME.apply(funded, P1, settle).state
    assert settled.buildings[settle.vertex] == Building(P1, "settlement")
    assert settled.hands[P1] == empty_hand()

    city_state = action_state(set_hand(settled, P1, CITY_COST))
    city_candidates = [
        action for action in listing(city_state) if isinstance(action, BuildCity)
    ]
    (city,) = city_candidates[:1]
    built = GAME.apply(city_state, P1, city).state
    assert built.buildings[city.vertex] == Building(P1, "city")
    assert built.hands[P1] == empty_hand()


def test_no_builds_without_cards() -> None:
    state, _ = play_setup()
    broke = action_state(set_hand(state, P1, empty_hand()))
    assert [action for action in listing(broke) if isinstance(action, PlaceRoad)] == []
    assert [
        action for action in listing(broke) if isinstance(action, PlaceSettlement)
    ] == []
    assert [action for action in listing(broke) if isinstance(action, BuildCity)] == []
    assert [action for action in listing(broke) if isinstance(action, BuyDev)] == []
    assert notation(broke)[0] == "end turn"


def test_bank_trade_uses_four_to_one_without_a_port() -> None:
    state, _ = play_setup()
    no_ports = replace(state, ports=(), phase="actions", dice=(1, 2))
    funded = set_hand(no_ports, P1, hand_from(wood=4))
    trade = BankTrade("wood", 4, "ore")
    assert GAME.format_action(trade) in notation(funded)
    after = GAME.apply(funded, P1, trade).state
    assert after.hands[P1] == hand_from(ore=1)
    with pytest.raises(IllegalActionError):
        GAME.apply(funded, P1, BankTrade("wood", 3, "ore"))


def test_ports_give_three_to_one_and_two_to_one_rates() -> None:
    state, _ = play_setup()
    edge = state.ports[0].edge
    vertex = EDGE_VERTICES[edge][0]
    buildings = list(state.buildings)
    buildings[vertex] = Building(P1, "settlement")
    generic = replace(
        state,
        ports=(Port(edge, None),),
        buildings=tuple(buildings),
    )
    assert trade_rates(generic, P1)["wood"] == 3
    specific = replace(state, ports=(Port(edge, "wood"),), buildings=tuple(buildings))
    assert trade_rates(specific, P1)["wood"] == 2
    assert trade_rates(specific, P1)["ore"] == 4


def test_player_offer_accept_transfers_one_card_each_way() -> None:
    state, _ = play_setup()
    hands = (
        hand_from(wood=1),
        hand_from(ore=1),
        empty_hand(),
    )
    offered = action_state(replace(state, hands=hands))
    offer = OfferTrade("wood", "ore", P2)
    assert offer in listing(offered)
    pending = GAME.apply(offered, P1, offer).state
    assert pending.phase == "trade_response"
    assert pending.pending_offer is not None
    assert [decision.player for decision in GAME.pending_decisions(pending)] == [P2]
    accepted = GAME.apply(pending, P2, AcceptOffer()).state
    assert accepted.phase == "actions"
    assert accepted.hands[P1] == hand_from(ore=1)
    assert accepted.hands[P2] == hand_from(wood=1)
    assert accepted.pending_offer is None


def test_offers_ignore_the_target_hand_and_accept_needs_the_card() -> None:
    state, _ = play_setup()
    offered = action_state(
        replace(state, hands=(hand_from(wood=1), empty_hand(), hand_from(ore=1)))
    )
    assert [a for a in listing(offered) if isinstance(a, OfferTrade)] == [
        OfferTrade("wood", take, target)
        for target in (P2, P3)
        for take in RESOURCES
        if take != "wood"
    ]
    to_p2 = GAME.apply(offered, P1, OfferTrade("wood", "ore", P2)).state
    assert notation(to_p2) == ["decline"]
    with pytest.raises(IllegalActionError, match="You have no ore to give"):
        GAME.apply(to_p2, P2, AcceptOffer())
    to_p3 = GAME.apply(offered, P1, OfferTrade("wood", "ore", P3)).state
    assert notation(to_p3) == ["accept", "decline"]


def test_declining_an_offer_returns_to_the_action_phase() -> None:
    state, _ = play_setup()
    offered = action_state(
        replace(state, hands=(hand_from(wood=1), hand_from(ore=1), empty_hand()))
    )
    offer = next(
        action for action in listing(offered) if isinstance(action, OfferTrade)
    )
    pending = GAME.apply(offered, P1, offer).state
    declined = GAME.apply(pending, P2, DeclineOffer()).state
    assert declined.phase == "actions"
    assert declined.pending_offer is None
    assert declined.hands == pending.hands


def test_offer_limit_ends_trade_talk_for_the_turn() -> None:
    config = CatanConfig(num_players=3, victory_points=5, max_offers_per_turn=1)
    state, _ = play_setup(config)
    offered = action_state(
        replace(
            state,
            hands=(
                hand_from(wood=2),
                hand_from(ore=2),
                hand_from(sheep=1),
            ),
        )
    )
    offer = next(
        action for action in listing(offered) if isinstance(action, OfferTrade)
    )
    pending = GAME.apply(offered, P1, offer).state
    declined = GAME.apply(pending, P2, DeclineOffer()).state
    assert declined.offers_this_turn == 1
    assert not any(isinstance(action, OfferTrade) for action in listing(declined))
    with pytest.raises(IllegalActionError, match="already made 1 offer"):
        GAME.apply(declined, P1, offer)


def test_discard_is_private_and_then_the_robber_moves() -> None:
    state, _ = play_setup()
    state = replace(
        state,
        phase="discard",
        hands=(hand_from(wood=2), empty_hand(), empty_hand()),
        discard_remaining=(2, 0, 0),
    )
    (decision,) = GAME.pending_decisions(state)
    assert decision.player == P1
    first = GAME.apply(state, P1, Discard("wood"))
    assert first.state.discard_remaining == (1, 0, 0)
    assert first.state.phase == "discard"
    private = [event for event in first.events if isinstance(event.audience, frozenset)]
    assert len(private) == 1
    assert private[0].audience == frozenset({P1})
    second = GAME.apply(first.state, P1, Discard("wood")).state
    assert second.phase == "move_robber"
    assert GAME.pending_decisions(second)[0].kind == "move_robber"


def test_robber_steal_conserves_cards() -> None:
    state, _ = play_setup()
    p2_hexes = [
        hex_id
        for hex_id in range(len(state.hexes))
        if hex_id != state.robber
        and any(building_at(state, vertex) == P2 for vertex in HEX_VERTICES[hex_id])
    ]
    assert p2_hexes
    rigged = replace(
        state,
        phase="move_robber",
        hands=(empty_hand(), hand_from(wood=3), empty_hand()),
    )
    hex_id = p2_hexes[0]
    move = next(
        action
        for action in listing(rigged)
        if isinstance(action, MoveRobber)
        and action.hex == hex_id
        and action.victim == P2
    )
    transition = GAME.apply(rigged, P1, move)
    assert transition.state.robber == hex_id
    assert hand_total(transition.state.hands[P1]) == 1
    assert hand_total(transition.state.hands[P2]) == 2
    assert hand_total(rigged.hands[P1]) + hand_total(rigged.hands[P2]) == 3
    assert any(event.kind == "stolen" for event in transition.events)


def test_robber_must_change_hex() -> None:
    state, _ = play_setup()
    moving = replace(state, phase="move_robber")
    moves = [action for action in listing(moving) if isinstance(action, MoveRobber)]
    assert all(action.hex != state.robber for action in moves)
    with pytest.raises(IllegalActionError, match="already on that hex"):
        GAME.apply(moving, P1, MoveRobber(state.robber, None))


def test_robber_never_lists_the_mover_as_a_victim() -> None:
    state = start()
    hex_id = next(hex_id for hex_id in range(19) if hex_id != state.robber)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[hex_id][0]] = Building(P1, "settlement")
    moving = replace(
        state,
        phase="move_robber",
        buildings=tuple(buildings),
        hands=(hand_from(wood=1), empty_hand(), empty_hand()),
    )
    assert [a for a in listing(moving) if a.hex == hex_id] == [MoveRobber(hex_id, None)]
    armed = replace(
        moving,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
    )
    knights = [a for a in listing(armed) if isinstance(a, PlayKnight)]
    assert [a for a in knights if a.hex == hex_id] == [PlayKnight(hex_id, None)]
    with pytest.raises(IllegalActionError, match="steal from yourself"):
        GAME.apply(moving, P1, MoveRobber(hex_id, P1))


def test_knight_moves_robber_and_counts_for_largest_army() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
    )
    knight = next(action for action in listing(armed) if isinstance(action, PlayKnight))
    transition = GAME.apply(armed, P1, knight)
    after = transition.state
    assert after.robber == knight.hex
    assert after.knights_played[P1] == 1
    assert after.dev_hands[P1] == empty_dev_hand()
    assert after.dev_played_this_turn is True
    assert not any(isinstance(action, PlayKnight) for action in listing(after))


def test_road_building_places_two_free_roads() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(road_building=1), empty_dev_hand(), empty_dev_hand()),
    )
    playing = GAME.apply(armed, P1, PlayRoadBuilding()).state
    assert playing.phase == "free_road"
    assert playing.free_roads == 2
    first = next(action for action in listing(playing) if isinstance(action, PlaceRoad))
    after_first = GAME.apply(playing, P1, first).state
    assert after_first.roads[first.edge] == P1
    assert after_first.free_roads == 1
    second = next(
        action for action in listing(after_first) if isinstance(action, PlaceRoad)
    )
    after_second = GAME.apply(after_first, P1, second).state
    assert after_second.phase == "actions"
    assert after_second.free_roads == 0


def test_year_of_plenty_and_monopoly() -> None:
    state, _ = play_setup()
    plenty = replace(
        state,
        phase="actions",
        dice=(1, 2),
        hands=(empty_hand(), empty_hand(), empty_hand()),
        dev_hands=(dev_hand_from(year_of_plenty=1), empty_dev_hand(), empty_dev_hand()),
    )
    after_plenty = GAME.apply(plenty, P1, PlayYearOfPlenty("wood", "ore")).state
    assert after_plenty.hands[P1] == hand_from(wood=1, ore=1)
    assert after_plenty.dev_hands[P1] == empty_dev_hand()

    monopoly = replace(
        state,
        phase="actions",
        dice=(1, 2),
        hands=(empty_hand(), hand_from(wood=3), empty_hand()),
        dev_hands=(dev_hand_from(monopoly=1), empty_dev_hand(), empty_dev_hand()),
    )
    after_monopoly = GAME.apply(monopoly, P1, PlayMonopoly("wood")).state
    assert after_monopoly.hands[P1] == hand_from(wood=3)
    assert after_monopoly.hands[P2] == empty_hand()


def test_buying_a_victory_point_card_can_win() -> None:
    config = CatanConfig(num_players=3, victory_points=3)
    state, _ = play_setup(config)
    funded = action_state(set_hand(state, P1, DEV_COST))
    rigged = replace(funded, dev_deck=("victory_point",), dev_hands=state.dev_hands)
    transition = GAME.apply(rigged, P1, BuyDev())
    assert transition.state.phase == "game_over"
    assert transition.state.winner == P1
    assert GAME.scores(transition.state).points[P1] == 3
    assert hand_total(transition.state.dev_hands[P1]) == 1


def test_victory_point_cards_are_hidden_from_opponents() -> None:
    state, _ = play_setup()
    hidden = replace(
        state,
        dev_hands=(dev_hand_from(victory_point=1), empty_dev_hand(), empty_dev_hand()),
    )
    public = GAME.observe(hidden, P2).data
    own = json_object(GAME.observe(hidden, P1).data, "you")
    points = number_values(public, "public_points")
    assert points[P1] == 2
    assert own["points"] == 3
    assert GAME.public_scores(hidden).points[P1] == 2
    assert GAME.scores(hidden).points[P1] == 3


def test_bought_cards_cannot_be_played_the_same_turn() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
        dev_bought=dev_hand_from(knight=1),
    )
    assert [action for action in listing(armed) if isinstance(action, PlayKnight)] == []


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


def test_longest_road_is_a_trail_through_both_rings_of_a_theta() -> None:
    first, second = next(hexes for hexes in EDGE_HEXES if len(hexes) == 2)
    roads: list[PlayerId | None] = [None] * 72
    for edge in (*HEX_EDGES[first], *HEX_EDGES[second]):
        roads[edge] = P1
    theta = replace(start(), roads=tuple(roads))
    assert roads.count(P1) == 11
    assert longest_road_length(theta, P1) == 11


def test_largest_army_keeps_ties_and_changes_on_a_strict_lead() -> None:
    state = start()
    three = replace(state, knights_played=(3, 0, 0), largest_army=None)
    awarded, _ = update_largest_army(three)
    assert awarded.largest_army == P1
    tied = replace(awarded, knights_played=(3, 3, 0))
    assert update_largest_army(tied)[0].largest_army == P1
    ahead = replace(awarded, knights_played=(3, 4, 0))
    assert update_largest_army(ahead)[0].largest_army == P2


def test_a_resource_cannot_be_removed_from_an_empty_hand() -> None:
    with pytest.raises(ValueError):
        hand_with(empty_hand(), "wood", -1)


def test_a_development_card_cannot_be_removed_from_an_empty_hand() -> None:
    with pytest.raises(ValueError):
        dev_with(empty_dev_hand(), "knight", -1)


def seven_seed() -> int:
    for seed in range(1000):
        first, rng = Rng.seeded(seed).roll(6)
        second, _ = rng.roll(6)
        if first + second == 7:
            return seed
    raise AssertionError("no seed rolls seven")


def test_discard_amount_after_a_seven() -> None:
    seed = seven_seed()
    state = replace(
        start(),
        rng=Rng.seeded(seed),
        hands=(hand_from(wheat=9), hand_from(wood=7), empty_hand()),
    )
    transition = GAME.roll_dice(state, P1)
    assert transition.state.phase == "discard"
    assert transition.state.discard_remaining == (4, 0, 0)


def test_robber_skips_empty_hands() -> None:
    state = start()
    hex_id = next(hex_id for hex_id in range(19) if hex_id != state.robber)
    buildings: list[Building | None] = [None] * 54
    buildings[HEX_VERTICES[hex_id][0]] = Building(P2, "settlement")
    buildings[HEX_VERTICES[hex_id][1]] = Building(P3, "settlement")
    state = replace(
        state,
        buildings=tuple(buildings),
        hands=(empty_hand(), empty_hand(), hand_from(wood=1)),
    )
    assert robber_victims(state, hex_id, P1) == (P3,)


def test_a_road_does_not_connect_through_an_opponent_building() -> None:
    state = start()
    vertex = 0
    edge, far_edge = VERTEX_EDGES[vertex][:2]
    roads: list[PlayerId | None] = [None] * 72
    roads[far_edge] = P1
    buildings: list[Building | None] = [None] * 54
    buildings[vertex] = Building(P2, "settlement")
    blocked = replace(state, buildings=tuple(buildings), roads=tuple(roads))
    assert not road_connected(blocked, edge, P1)
    open_state = replace(blocked, buildings=(None,) * 54)
    assert road_connected(open_state, edge, P1)


def test_an_unbroken_longest_road_holder_keeps_a_tie() -> None:
    assert longest_road_holder((5, 5, 0), P1, is_broken=False) == P1
    assert longest_road_holder((5, 5, 0), None, is_broken=False) is None


def test_settlement_piece_limit_stops_the_listing() -> None:
    state = start()
    target = 0
    roads: list[PlayerId | None] = [None] * 72
    roads[VERTEX_EDGES[target][0]] = P1
    buildings: list[Building | None] = [None] * 54
    far = [
        vertex
        for vertex in range(54)
        if vertex != target and vertex not in VERTEX_NEIGHBORS[target]
    ][:MAX_SETTLEMENTS]
    for vertex in far:
        buildings[vertex] = Building(P1, "settlement")
    state = action_state(
        replace(state, roads=tuple(roads), buildings=tuple(buildings), active=P1)
    )
    state = set_hand(state, P1, SETTLEMENT_COST)
    assert not settlement_pieces_available(state, P1)
    assert not any(isinstance(action, PlaceSettlement) for action in listing(state))


def test_city_piece_limit_stops_the_listing() -> None:
    state = start()
    buildings: list[Building | None] = [None] * 54
    for vertex in range(MAX_CITIES):
        buildings[vertex] = Building(P1, "city")
    buildings[MAX_CITIES] = Building(P1, "settlement")
    state = replace(state, buildings=tuple(buildings))
    assert not city_legal(state, MAX_CITIES, P1)


def test_road_building_stops_after_the_last_piece() -> None:
    state, _ = play_setup()
    path = path_edges(MAX_ROADS - 1)
    roads: list[PlayerId | None] = [None] * 72
    for edge in path:
        roads[edge] = P1
    armed = replace(
        state,
        roads=tuple(roads),
        phase="actions",
        dice=(1, 2),
        active=P1,
        dev_hands=(
            dev_hand_from(road_building=1),
            empty_dev_hand(),
            empty_dev_hand(),
        ),
    )
    playing = GAME.apply(armed, P1, PlayRoadBuilding()).state
    free_road = next(
        action for action in listing(playing) if isinstance(action, PlaceRoad)
    )
    after = GAME.apply(playing, P1, free_road).state
    assert after.phase == "actions"
    assert after.free_roads == 0


def test_only_one_development_card_can_be_played_per_turn() -> None:
    state, _ = play_setup()
    armed = replace(
        state,
        phase="actions",
        dice=(1, 2),
        dev_hands=(
            dev_hand_from(knight=1, year_of_plenty=1),
            empty_dev_hand(),
            empty_dev_hand(),
        ),
    )
    knight = next(action for action in listing(armed) if isinstance(action, PlayKnight))
    after = GAME.apply(armed, P1, knight).state
    assert not any(isinstance(action, PlayYearOfPlenty) for action in listing(after))


def test_harbour_needs_your_own_building() -> None:
    state, _ = play_setup()
    edge = state.ports[0].edge
    no_building = replace(state, ports=(Port(edge, None),), buildings=(None,) * 54)
    assert trade_rates(no_building, P1)["wood"] == 4
    buildings: list[Building | None] = [None] * 54
    buildings[EDGE_VERTICES[edge][0]] = Building(P2, "settlement")
    opponent = replace(no_building, buildings=tuple(buildings))
    assert trade_rates(opponent, P1)["wood"] == 4
    buildings[EDGE_VERTICES[edge][0]] = Building(P1, "settlement")
    owned = replace(no_building, buildings=tuple(buildings))
    assert trade_rates(owned, P1)["wood"] == 3


def test_no_city_on_another_players_settlement() -> None:
    state, _ = play_setup()
    vertex = 0
    buildings: list[Building | None] = [None] * 54
    buildings[vertex] = Building(P2, "settlement")
    state = replace(state, buildings=tuple(buildings), phase="actions", dice=(1, 2))
    assert not city_legal(state, vertex, P1)
    assert BuildCity(vertex) not in listing(state)


def test_notation_round_trips_every_action() -> None:
    actions: list[Action] = [
        Roll(),
        EndTurn(),
        PlaceSettlement(3),
        PlaceRoad(4),
        BuildCity(3),
        BuyDev(),
        Discard("wood"),
        MoveRobber(5, P2),
        MoveRobber(5, None),
        BankTrade("wood", 4, "ore"),
        OfferTrade("wood", "ore", P2),
        AcceptOffer(),
        DeclineOffer(),
        PlayKnight(5, P2),
        PlayRoadBuilding(),
        PlayYearOfPlenty("ore", "wood"),
        PlayMonopoly("wood"),
    ]
    for action in actions:
        assert GAME.parse_action(GAME.format_action(action)) == action


def test_year_of_plenty_keeps_both_resources_in_resource_order() -> None:
    reversed_pair = GAME.parse_action("play yearofplenty ore wood")
    assert isinstance(reversed_pair, PlayYearOfPlenty)
    assert (reversed_pair.first, reversed_pair.second) == ("wood", "ore")
    assert GAME.format_action(reversed_pair) == "play yearofplenty wood ore"
    for action in (PlayYearOfPlenty("ore", "wood"), PlayYearOfPlenty("wood", "ore")):
        assert GAME.parse_action(GAME.format_action(action)) == action
        assert action == reversed_pair


@pytest.mark.parametrize(
    "text",
    [
        "roll ",
        "end",
        "settle v01",
        "settle V1",
        "road e-1",
        "bank 0 wood for 1 ore",
        "bank 4 wood for 2 ore",
        "offer wood for wood to P0",
        "play knight h5 P0",
        "play yearofplenty wood",
        "discard",
        "robber h5 p2",
        "play road building",
    ],
)
def test_parse_rejects_non_canonical_text(text: str) -> None:
    with pytest.raises(NotationError):
        GAME.parse_action(text)


def test_off_board_ids_parse_but_are_illegal() -> None:
    action = GAME.parse_action("settle v999")
    state, _ = play_setup()
    with pytest.raises(IllegalActionError, match="not on the board"):
        GAME.apply(action_state(state), P1, action)


def test_observation_ignores_other_players_hidden_cards() -> None:
    state, _ = play_setup()
    viewer = P2
    original = replace(
        state,
        phase="actions",
        hands=(hand_from(wood=3), hand_from(ore=2), empty_hand()),
        dev_hands=(dev_hand_from(knight=1), empty_dev_hand(), empty_dev_hand()),
    )
    changed = replace(
        original,
        hands=(hand_from(ore=3), hand_from(ore=2), empty_hand()),
        dev_hands=(dev_hand_from(victory_point=1), empty_dev_hand(), empty_dev_hand()),
        dev_deck=tuple(reversed(original.dev_deck)),
        rng=Rng(original.rng.state + 1),
    )
    for observer in (viewer, None):
        assert GAME.observe(original, observer) == GAME.observe(changed, observer)
        assert GAME.render_text(GAME.observe(original, observer)) == GAME.render_text(
            GAME.observe(changed, observer)
        )


def test_render_text_and_descriptions_name_the_board() -> None:
    state, _ = play_setup()
    observation = GAME.observe(action_state(state), P1)
    text = GAME.render_text(observation)
    assert "You are P1." in text
    assert "Hexes:" in text
    assert "Intersections:" in text
    assert "Paths:" in text
    assert "Your hand:" in text
    vertex = HEX_VERTICES[0][0]
    described = GAME.describe_action(observation, PlaceSettlement(vertex))
    assert f"v{vertex}" in described
    edge = VERTEX_EDGES[vertex][0]
    assert f"e{edge}" in GAME.describe_action(observation, PlaceRoad(edge))


def test_game_over_render_shows_final_points_and_revealed_cards() -> None:
    config = CatanConfig(num_players=3, victory_points=3)
    state, _ = play_setup(config)
    funded = action_state(set_hand(state, P1, DEV_COST))
    rigged = replace(funded, dev_deck=("victory_point",), dev_hands=state.dev_hands)
    over = GAME.apply(rigged, P1, BuyDev()).state
    text = GAME.render_text(GAME.observe(over, P2))
    assert "  P1: 3 VP (settlements 2, victory cards 1);" in text
    assert "Revealed hands:" in text
    assert "development cards: knight 0, roadbuilding 0, yearofplenty 0, " in text
    assert "monopoly 0, victorypoint 1." in text


def test_render_and_rules_name_development_cards_as_notation_does() -> None:
    state, _ = play_setup()
    armed = action_state(
        replace(
            state,
            dev_hands=(
                dev_hand_from(road_building=1),
                empty_dev_hand(),
                empty_dev_hand(),
            ),
        )
    )
    observation = GAME.observe(armed, P1)
    text = GAME.render_text(observation)
    rules = GAME.rules_text()
    assert "Your development cards: knight 0, roadbuilding 1, yearofplenty 0" in text
    assert "roadbuilding" in GAME.describe_action(observation, PlayRoadBuilding())
    for name in ("knight", "roadbuilding", "yearofplenty", "monopoly", "victorypoint"):
        assert f"`{name}`" in rules
    for spelling in ("road_building", "Road Building", "Year of Plenty"):
        assert spelling not in text
        assert spelling not in rules


def test_observation_and_render_show_the_development_deck_size() -> None:
    state, _ = play_setup()
    shorter = replace(state, dev_deck=state.dev_deck[:7])
    for viewer in (P1, None):
        observation = GAME.observe(shorter, viewer)
        assert observation.data["dev_deck_size"] == 7
        assert "Development deck: 7 cards left." in GAME.render_text(observation)


def test_config_validation_and_registry() -> None:
    assert GAME.parse_config({}) == CatanConfig()
    assert GAME.parse_config(GAME.config_json(CONFIG)) == CONFIG
    for raw in (
        {"num_players": 2},
        {"num_players": 5},
        {"victory_points": 2},
        {"max_offers_per_turn": 21},
    ):
        with pytest.raises(ConfigError):
            GAME.parse_config(raw)
    assert isinstance(create_game("catan"), Catan)


def test_same_seed_replays_to_the_same_log() -> None:
    config = CatanConfig(num_players=3, victory_points=4)
    first = record_match(config, 4)
    second = record_match(config, 4)
    assert first == second
    report = replay_match(first)
    assert report.game_id == "catan"
    assert report.steps > 0


def check_playthrough_state(state: CatanState) -> None:
    """Cards never go negative and award holders meet the minimums."""
    assert all(hand_total(hand) >= 0 for hand in state.hands)
    assert all(all(card >= 0 for card in hand) for hand in state.dev_hands)
    if state.longest_road is not None:
        assert longest_road_lengths(state)[state.longest_road] >= 5
    if state.largest_army is not None:
        assert state.knights_played[state.largest_army] >= 3
    if state.phase == "discard":
        assert any(state.discard_remaining)
    return


def test_random_playthroughs_reach_ten_points_and_build_a_city() -> None:
    config = CatanConfig(num_players=3)
    cities = 0
    for seed in (3,):
        state, _ = random_playthrough(GAME, config, seed, check_playthrough_state)
        assert state.winner is not None
        assert GAME.scores(state).points[state.winner] >= config.victory_points == 10
        cities += sum(
            1
            for building in state.buildings
            if building is not None and building.kind == "city"
        )
    assert cities >= 1


def number_values(data: JsonObject, key: str) -> list[float]:
    """A JSON list of numbers, as floats."""
    return [
        float(value)
        for value in list_of_values(key, data[key])
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]


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
