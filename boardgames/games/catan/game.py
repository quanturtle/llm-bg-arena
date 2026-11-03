"""Catan: the standard 19-hex base game for 3 or 4 players.

The board is fixed geometry; terrain, number tokens, ports and the development
deck are shuffled from the match seed. Hidden information is each player's
resource hand and development cards. A move is a small notation such as
`settle v12`, `road e34`, `bank 4 wood for 1 ore` or `end turn`.
"""

from dataclasses import replace
from functools import partial
from importlib.resources import files
from typing import ClassVar

from boardgames.core import (
    ConfigError,
    Decision,
    Event,
    FlatActionSpace,
    IllegalActionError,
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    Rng,
    Scores,
    Transition,
    register_game,
    seat_label,
    seats,
)
from boardgames.core.actions import ActionSpace
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)
from boardgames.games.catan.geometry import (
    EDGE_VERTICES,
    PORT_EDGES,
    VERTEX_EDGES,
    VERTEX_HEXES,
)
from boardgames.games.catan.model import (
    CITY_COST,
    DEV_COST,
    DEV_DECK_COUNTS,
    LARGEST_ARMY_MINIMUM,
    LONGEST_ROAD_MINIMUM,
    NUMBER_TOKENS,
    RESOURCES,
    ROAD_COST,
    SETTLEMENT_COST,
    TERRAIN_DECK,
    TERRAIN_RESOURCE,
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    Building,
    BuyDev,
    CatanConfig,
    CatanState,
    DeclineOffer,
    DevCard,
    Discard,
    EndTurn,
    Hand,
    Hex,
    MoveRobber,
    Offer,
    OfferTrade,
    Phase,
    PlaceRoad,
    PlaceSettlement,
    PlayKnight,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
    Port,
    Resource,
    Roll,
    can_afford,
    dev_get,
    dev_with,
    empty_hand,
    hand_cards,
    hand_get,
    hand_json,
    hand_minus,
    hand_plus,
    hand_total,
    hand_with,
    point_breakdown,
    total_points,
)
from boardgames.games.catan.notation import format_action, parse_action
from boardgames.games.catan.rules import (
    city_legal,
    distance_rule_ok,
    legal_free_road_edges,
    longest_road_lengths,
    production,
    road_legal,
    robber_victims,
    settlement_connected,
    settlement_legal,
    settlement_pieces_available,
    setup_road_legal,
    setup_settlement_legal,
    trade_rates,
)
from boardgames.games.catan.view import (
    describe_action,
    observe,
    render_text,
)

DISCARD_THRESHOLD = 7


@register_game
class Catan:
    """Standard Catan with settlements, cities, roads, trade and development cards."""

    id: ClassVar[str] = "catan"

    def parse_config(self, raw: JsonObject) -> CatanConfig:
        config = dataclass_from_json(CatanConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: CatanConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    def setup(self, config: CatanConfig, seed: int) -> Transition[CatanState]:
        rng = Rng.seeded(seed)
        terrains, rng = rng.shuffled(TERRAIN_DECK)
        board_hexes: list[Hex] = [Hex(terrain, None) for terrain in terrains]
        numbers, rng = rng.shuffled(NUMBER_TOKENS)
        number_index = 0
        for hex_id, board_hex in enumerate(board_hexes):
            if board_hex.terrain == "desert":
                continue
            board_hexes[hex_id] = replace(board_hex, number=numbers[number_index])
            number_index += 1

        port_kinds: tuple[Resource | None, ...] = (None, None, None, None, *RESOURCES)
        shuffled_ports, rng = rng.shuffled(port_kinds)
        ports = tuple(
            Port(edge, kind)
            for edge, kind in zip(PORT_EDGES, shuffled_ports, strict=True)
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
            hexes=tuple(board_hexes),
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
            dev_hands=(empty_hand(),) * player_count,
            knights_played=(0,) * player_count,
            longest_road=None,
            largest_army=None,
            dev_bought=empty_hand(),
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

    def pending_decisions(self, state: CatanState) -> tuple[Decision, ...]:
        if state.phase == "game_over":
            return ()
        if state.phase == "discard":
            for player in seats(state.config.num_players):
                remaining = state.discard_remaining[player]
                if remaining:
                    return (
                        Decision(
                            player,
                            "discard",
                            f"Discard {remaining} cards after a 7; choose one card.",
                        ),
                    )
            return ()
        if state.phase == "trade_response":
            offer = state.pending_offer
            if offer is None:
                return ()
            return (
                Decision(
                    offer.to_player,
                    "trade_response",
                    f"Answer {seat_label(offer.from_player)}'s offer: "
                    f"1 {offer.give} for 1 {offer.take}. Accept or decline.",
                ),
            )
        return (
            Decision(
                state.active,
                decision_kind(state.phase),
                decision_prompt(state),
            ),
        )

    def legal_actions(
        self, state: CatanState, decision: Decision
    ) -> ActionSpace[Action]:
        actions = legal_action_list(state, decision.player)
        default = default_action(state, actions)
        return FlatActionSpace(
            actions,
            format_action,
            explain=partial(explain_illegal, state, decision.player),
            default=default,
        )

    def apply(
        self, state: CatanState, player: PlayerId, action: Action
    ) -> Transition[CatanState]:
        decision = next(
            (item for item in self.pending_decisions(state) if item.player == player),
            None,
        )
        if decision is None:
            raise IllegalActionError(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            )
        space = self.legal_actions(state, decision)
        try:
            is_legal = space.is_legal(action)
        except (TypeError, ValueError, AttributeError) as error:
            raise IllegalActionError(
                f"{seat_label(player)} proposed an unknown action: {error}"
            ) from error
        if not is_legal:
            try:
                reason = space.explain(action)
            except (TypeError, ValueError, IndexError, AttributeError) as error:
                reason = f"that action is not legal now ({error})"
            raise IllegalActionError(reason)
        return self.apply_legal(state, player, action)

    def apply_legal(
        self, state: CatanState, player: PlayerId, action: Action
    ) -> Transition[CatanState]:
        """Apply an action already checked by `legal_actions`."""
        if state.phase == "setup_settlement":
            if not isinstance(action, PlaceSettlement):
                raise IllegalActionError("only a settlement is legal during setup")
            return self.place_setup_settlement(state, player, action.vertex)
        if state.phase == "setup_road":
            if not isinstance(action, PlaceRoad):
                raise IllegalActionError("only a road is legal during setup")
            return self.place_setup_road(state, player, action.edge)
        if state.phase == "roll":
            return self.roll_dice(state, player)
        if state.phase == "discard":
            if not isinstance(action, Discard):
                raise IllegalActionError("only discards are legal now")
            return self.discard_card(state, player, action.resource)
        if state.phase == "move_robber":
            if not isinstance(action, MoveRobber):
                raise IllegalActionError("move the robber now")
            return self.move_robber(state, player, action.hex, action.victim)
        if state.phase == "free_road":
            if not isinstance(action, PlaceRoad):
                raise IllegalActionError("place a free road now")
            return self.place_free_road(state, player, action.edge)
        if state.phase == "trade_response":
            if isinstance(action, AcceptOffer):
                return self.accept_offer(state, player)
            if isinstance(action, DeclineOffer):
                return self.decline_offer(state, player)
            raise IllegalActionError("accept or decline the offer")
        if state.phase != "actions":
            raise IllegalActionError(f"no action is legal in phase {state.phase!r}")
        return self.apply_action_phase(state, player, action)

    def is_terminal(self, state: CatanState) -> bool:
        return state.phase == "game_over"

    def scores(self, state: CatanState) -> Scores:
        breakdown = {
            player: point_breakdown(state, player, include_hidden=True)
            for player in seats(state.config.num_players)
        }
        points = {player: sum(parts.values()) for player, parts in breakdown.items()}
        return Scores(points, breakdown)

    def observe(self, state: CatanState, viewer: PlayerId | None) -> Observation:
        return observe(state, viewer)

    def render_text(self, observation: Observation) -> str:
        return render_text(observation)

    def rules_text(self) -> str:
        rules = files("boardgames.games.catan") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Action) -> str:
        return format_action(action)

    def parse_action(self, text: str) -> Action:
        return parse_action(text)

    def describe_action(self, observation: Observation, action: Action) -> str:
        return describe_action(observation, action)

    def action_json(self, action: Action) -> dict[str, JsonValue]:
        return tagged_json_object(action)

    # Setup ---------------------------------------------------------------

    def place_setup_settlement(
        self, state: CatanState, player: PlayerId, vertex: int
    ) -> Transition[CatanState]:
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
        if not setup_road_edges(new_state, vertex):
            events.append(
                Event(
                    "setup_road_skipped",
                    f"No empty path touches v{vertex}; the setup road is skipped.",
                    {"player": player, "vertex": vertex},
                )
            )
            skipped_state, next_events = advance_setup(
                replace(new_state, setup_vertex=None)
            )
            return Transition(skipped_state, tuple([*events, *next_events]))
        return Transition(new_state, tuple(events))

    def place_setup_road(
        self, state: CatanState, player: PlayerId, edge: int
    ) -> Transition[CatanState]:
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

    # Turn phases ---------------------------------------------------------

    def roll_dice(self, state: CatanState, player: PlayerId) -> Transition[CatanState]:
        first, rng = state.rng.roll(6)
        second, rng = rng.roll(6)
        total = first + second
        events = [
            Event(
                "dice_rolled",
                f"{seat_label(player)} rolled {first} + {second} = {total}.",
                {"player": player, "dice": [first, second], "total": total},
            )
        ]
        rolled = replace(state, rng=rng, dice=(first, second))
        if total == 7:
            remaining = tuple(
                hand_total(hand) // 2 if hand_total(hand) > DISCARD_THRESHOLD else 0
                for hand in state.hands
            )
            owed = [
                f"{seat_label(PlayerId(seat))} {count}"
                for seat, count in enumerate(remaining)
                if count
            ]
            events.append(
                Event(
                    "seven_rolled",
                    "A 7 is rolled. "
                    + (
                        "Discards: " + ", ".join(owed) + "."
                        if owed
                        else "No one holds more than seven cards."
                    ),
                    {"discard": list(remaining)},
                )
            )
            phase: Phase = "discard" if any(remaining) else "move_robber"
            return Transition(
                replace(
                    rolled,
                    phase=phase,
                    discard_remaining=remaining,
                    dev_played_this_turn=False,
                ),
                tuple(events),
            )
        gains = production(state, total)
        hands = tuple(
            hand_plus(hand, gain) for hand, gain in zip(state.hands, gains, strict=True)
        )
        events.append(production_event(gains, total))
        return Transition(
            replace(rolled, hands=hands, phase="actions"),
            tuple(events),
        )

    def discard_card(
        self, state: CatanState, player: PlayerId, resource: Resource
    ) -> Transition[CatanState]:
        hand = state.hands[player]
        if hand_get(hand, resource) < 1:
            raise IllegalActionError(f"you have no {resource} to discard")
        hands = replace_at(state.hands, player, hand_with(hand, resource, -1))
        remaining = list(state.discard_remaining)
        remaining[player] -= 1
        events = [
            Event(
                "discarded",
                f"{seat_label(player)} discarded 1 {resource}.",
                {"player": player, "resource": resource},
                audience=frozenset({player}),
            ),
            Event(
                "discard_notice",
                f"{seat_label(player)} discarded a card.",
                {"player": player},
            ),
        ]
        phase: Phase = (
            "move_robber" if all(count == 0 for count in remaining) else "discard"
        )
        return Transition(
            replace(
                state,
                hands=hands,
                discard_remaining=tuple(remaining),
                phase=phase,
            ),
            tuple(events),
        )

    def move_robber(
        self,
        state: CatanState,
        player: PlayerId,
        hex_id: int,
        victim: PlayerId | None,
    ) -> Transition[CatanState]:
        moved, events = move_robber_and_steal(state, player, hex_id, victim)
        return Transition(replace(moved, phase="actions"), tuple(events))

    def place_free_road(
        self, state: CatanState, player: PlayerId, edge: int
    ) -> Transition[CatanState]:
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
        built, award_events = update_longest_road(built)
        events.extend(award_events)
        finished = finish_if_won(built, tuple(events))
        if finished.state.phase == "game_over":
            return finished
        if free_roads > 0 and legal_free_road_edges(finished.state, player):
            return Transition(
                replace(finished.state, phase="free_road"), finished.events
            )
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

    def apply_action_phase(
        self, state: CatanState, player: PlayerId, action: Action
    ) -> Transition[CatanState]:
        if isinstance(action, PlaceRoad):
            return self.build_road(state, player, action.edge)
        if isinstance(action, PlaceSettlement):
            return self.build_settlement(state, player, action.vertex)
        if isinstance(action, BuildCity):
            return self.build_city(state, player, action.vertex)
        if isinstance(action, BuyDev):
            return self.buy_dev(state, player)
        if isinstance(action, BankTrade):
            return self.bank_trade(state, player, action)
        if isinstance(action, OfferTrade):
            return self.offer_trade(state, player, action)
        if isinstance(action, PlayKnight):
            return self.play_knight(state, player, action.hex, action.victim)
        if isinstance(action, PlayRoadBuilding):
            return self.play_road_building(state, player)
        if isinstance(action, PlayYearOfPlenty):
            return self.play_year_of_plenty(state, player, action.first, action.second)
        if isinstance(action, PlayMonopoly):
            return self.play_monopoly(state, player, action.resource)
        if isinstance(action, EndTurn):
            return self.end_turn(state, player)
        raise IllegalActionError("that action is not available in the action phase")

    # Building and trading ------------------------------------------------

    def build_road(
        self, state: CatanState, player: PlayerId, edge: int
    ) -> Transition[CatanState]:
        paid = pay_cost(state, player, ROAD_COST)
        roads = replace_at(paid.roads, edge, player)
        events = [
            Event(
                "road_built",
                f"{seat_label(player)} built a road on e{edge}.",
                {"player": player, "edge": edge},
            )
        ]
        built, award_events = update_longest_road(replace(paid, roads=roads))
        events.extend(award_events)
        return finish_if_won(built, tuple(events))

    def build_settlement(
        self, state: CatanState, player: PlayerId, vertex: int
    ) -> Transition[CatanState]:
        paid = pay_cost(state, player, SETTLEMENT_COST)
        buildings = replace_at(paid.buildings, vertex, Building(player, "settlement"))
        events = [
            Event(
                "settlement_built",
                f"{seat_label(player)} built a settlement on v{vertex}.",
                {"player": player, "vertex": vertex},
            )
        ]
        built, award_events = update_longest_road(replace(paid, buildings=buildings))
        events.extend(award_events)
        return finish_if_won(built, tuple(events))

    def build_city(
        self, state: CatanState, player: PlayerId, vertex: int
    ) -> Transition[CatanState]:
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

    def buy_dev(self, state: CatanState, player: PlayerId) -> Transition[CatanState]:
        paid = pay_cost(state, player, DEV_COST)
        card = paid.dev_deck[0]
        dev_hands = replace_at(
            paid.dev_hands, player, dev_with(paid.dev_hands[player], card)
        )
        dev_bought = dev_with(paid.dev_bought, card)
        events = [
            Event(
                "dev_bought",
                f"{seat_label(player)} bought a development card.",
                {"player": player},
            ),
            Event(
                "dev_drawn",
                f"You drew a {dev_name(card)}.",
                {"player": player, "card": card},
                audience=frozenset({player}),
            ),
        ]
        bought = replace(
            paid,
            dev_deck=paid.dev_deck[1:],
            dev_hands=dev_hands,
            dev_bought=dev_bought,
        )
        return finish_if_won(bought, tuple(events))

    def bank_trade(
        self, state: CatanState, player: PlayerId, action: BankTrade
    ) -> Transition[CatanState]:
        cost = hand_with(empty_hand(), action.give, action.give_count)
        hand = hand_minus(state.hands[player], cost)
        if hand is None:
            raise IllegalActionError("you do not have the cards for that bank trade")
        hand = hand_with(hand, action.take, 1)
        events = [
            Event(
                "bank_trade",
                f"{seat_label(player)} traded {action.give_count} {action.give} "
                f"for 1 {action.take} with the bank.",
                {
                    "player": player,
                    "give": action.give,
                    "give_count": action.give_count,
                    "take": action.take,
                },
            )
        ]
        return Transition(
            replace(state, hands=replace_at(state.hands, player, hand)),
            tuple(events),
        )

    def offer_trade(
        self, state: CatanState, player: PlayerId, action: OfferTrade
    ) -> Transition[CatanState]:
        offer = Offer(player, action.target, action.give, action.take)
        events = [
            Event(
                "offer_made",
                f"{seat_label(player)} offers {seat_label(action.target)} "
                f"1 {action.give} for 1 {action.take}.",
                {
                    "from": player,
                    "to": action.target,
                    "give": action.give,
                    "take": action.take,
                },
            )
        ]
        return Transition(
            replace(
                state,
                pending_offer=offer,
                phase="trade_response",
                offers_this_turn=state.offers_this_turn + 1,
            ),
            tuple(events),
        )

    def accept_offer(
        self, state: CatanState, player: PlayerId
    ) -> Transition[CatanState]:
        offer = state.pending_offer
        if offer is None or offer.to_player != player:
            raise IllegalActionError("there is no offer for you to accept")
        giver = offer.from_player
        giver_hand = state.hands[giver]
        taker_hand = state.hands[player]
        if hand_get(giver_hand, offer.give) < 1:
            raise IllegalActionError("the offering player no longer has that card")
        if hand_get(taker_hand, offer.take) < 1:
            raise IllegalActionError("you no longer have the requested card")
        giver_hand = hand_with(hand_with(giver_hand, offer.give, -1), offer.take)
        taker_hand = hand_with(hand_with(taker_hand, offer.take, -1), offer.give)
        hands = replace_at(
            replace_at(state.hands, giver, giver_hand), player, taker_hand
        )
        events = [
            Event(
                "offer_accepted",
                f"{seat_label(player)} accepted: {seat_label(giver)} gave "
                f"1 {offer.give} for 1 {offer.take}.",
                {
                    "from": giver,
                    "to": player,
                    "give": offer.give,
                    "take": offer.take,
                },
            )
        ]
        return Transition(
            replace(state, hands=hands, pending_offer=None, phase="actions"),
            tuple(events),
        )

    def decline_offer(
        self, state: CatanState, player: PlayerId
    ) -> Transition[CatanState]:
        offer = state.pending_offer
        if offer is None or offer.to_player != player:
            raise IllegalActionError("there is no offer for you to decline")
        events = [
            Event(
                "offer_declined",
                f"{seat_label(player)} declined the offer.",
                {"from": offer.from_player, "to": player},
            )
        ]
        return Transition(
            replace(state, pending_offer=None, phase="actions"),
            tuple(events),
        )

    # Development cards ---------------------------------------------------

    def play_knight(
        self,
        state: CatanState,
        player: PlayerId,
        hex_id: int,
        victim: PlayerId | None,
    ) -> Transition[CatanState]:
        dev_hands = replace_at(
            state.dev_hands, player, dev_with(state.dev_hands[player], "knight", -1)
        )
        knights = list(state.knights_played)
        knights[player] += 1
        events = [
            Event(
                "knight_played",
                f"{seat_label(player)} played a knight.",
                {"player": player},
            )
        ]
        moved, robber_events = move_robber_and_steal(
            replace(
                state,
                dev_hands=dev_hands,
                knights_played=tuple(knights),
                dev_played_this_turn=True,
            ),
            player,
            hex_id,
            victim,
        )
        events.extend(robber_events)
        moved, award_events = update_largest_army(moved)
        events.extend(award_events)
        return finish_if_won(replace(moved, phase="actions"), tuple(events))

    def play_road_building(
        self, state: CatanState, player: PlayerId
    ) -> Transition[CatanState]:
        dev_hands = replace_at(
            state.dev_hands,
            player,
            dev_with(state.dev_hands[player], "road_building", -1),
        )
        events = [
            Event(
                "road_building_played",
                f"{seat_label(player)} played Road Building.",
                {"player": player},
            )
        ]
        prepared = replace(
            state,
            dev_hands=dev_hands,
            dev_played_this_turn=True,
            free_roads=2,
        )
        phase: Phase = (
            "free_road" if legal_free_road_edges(prepared, player) else "actions"
        )
        return Transition(replace(prepared, phase=phase), tuple(events))

    def play_year_of_plenty(
        self,
        state: CatanState,
        player: PlayerId,
        first: Resource,
        second: Resource,
    ) -> Transition[CatanState]:
        dev_hands = replace_at(
            state.dev_hands,
            player,
            dev_with(state.dev_hands[player], "year_of_plenty", -1),
        )
        hand = hand_with(hand_with(state.hands[player], first, 1), second, 1)
        events = [
            Event(
                "year_of_plenty_played",
                f"{seat_label(player)} played Year of Plenty and took "
                f"1 {first} and 1 {second}.",
                {"player": player, "first": first, "second": second},
            )
        ]
        return Transition(
            replace(
                state,
                dev_hands=dev_hands,
                hands=replace_at(state.hands, player, hand),
                dev_played_this_turn=True,
            ),
            tuple(events),
        )

    def play_monopoly(
        self, state: CatanState, player: PlayerId, resource: Resource
    ) -> Transition[CatanState]:
        dev_hands = replace_at(
            state.dev_hands,
            player,
            dev_with(state.dev_hands[player], "monopoly", -1),
        )
        hands = list(state.hands)
        taken: dict[str, int] = {}
        total = 0
        for other in seats(state.config.num_players):
            if other == player:
                continue
            count = hand_get(hands[other], resource)
            if count:
                taken[str(other)] = count
                total += count
                hands[other] = hand_with(hands[other], resource, -count)
        hands[player] = hand_with(hands[player], resource, total)
        events = [
            Event(
                "monopoly_played",
                f"{seat_label(player)} played Monopoly on {resource} and took "
                f"{total} card{'s' if total != 1 else ''}.",
                {
                    "player": player,
                    "resource": resource,
                    "taken": taken,
                    "total": total,
                },
            )
        ]
        return Transition(
            replace(
                state,
                dev_hands=dev_hands,
                hands=tuple(hands),
                dev_played_this_turn=True,
            ),
            tuple(events),
        )

    # Ending a turn -------------------------------------------------------

    def end_turn(self, state: CatanState, player: PlayerId) -> Transition[CatanState]:
        next_player = PlayerId((player + 1) % state.config.num_players)
        events = [
            Event(
                "turn_ended",
                f"{seat_label(player)} ended their turn.",
                {"player": player},
            ),
            Event(
                "turn_started",
                f"{seat_label(next_player)}'s turn.",
                {"player": next_player},
            ),
        ]
        return Transition(
            replace(
                state,
                active=next_player,
                turn=state.turn + 1,
                phase="roll",
                dice=None,
                free_roads=0,
                offers_this_turn=0,
                dev_bought=empty_hand(),
                dev_played_this_turn=False,
                pending_offer=None,
                discard_remaining=(0,) * state.config.num_players,
            ),
            tuple(events),
        )


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


def setup_order(config: CatanConfig) -> tuple[PlayerId, ...]:
    """Settlement order: clockwise, then back counter-clockwise."""
    forward = tuple(PlayerId(index) for index in range(config.num_players))
    return (*forward, *reversed(forward))


def decision_kind(phase: str) -> str:
    """Decision kind recorded in logs for a phase."""
    return {
        "setup_settlement": "setup_settlement",
        "setup_road": "setup_road",
        "roll": "roll",
        "move_robber": "move_robber",
        "actions": "action",
        "free_road": "free_road",
    }.get(phase, phase)


def decision_prompt(state: CatanState) -> str:
    """What the phase asks the active player to do."""
    if state.phase == "setup_settlement":
        return "Place a settlement on an empty intersection."
    if state.phase == "setup_road":
        vertex = state.setup_vertex
        return f"Place a road touching your new settlement on v{vertex}."
    if state.phase == "roll":
        return "Roll the two dice."
    if state.phase == "move_robber":
        return "Move the robber to a different hex and steal if possible."
    if state.phase == "free_road":
        return f"Place a free road ({state.free_roads} left)."
    if state.phase == "actions":
        return "Build, trade, play a development card, or end your turn."
    return "Choose an action."


def default_action(state: CatanState, actions: list[Action]) -> Action | None:
    """A safe fallback for each phase."""
    if state.phase == "roll":
        return Roll()
    if state.phase == "actions":
        return EndTurn()
    if state.phase == "trade_response":
        return DeclineOffer()
    return None


def legal_action_list(state: CatanState, player: PlayerId) -> list[Action]:
    """Every legal action in the current phase, in a stable, readable order."""
    if state.phase == "setup_settlement":
        return [
            PlaceSettlement(vertex)
            for vertex in range(len(state.buildings))
            if setup_settlement_legal(state, vertex)
        ]
    if state.phase == "setup_road":
        if state.setup_vertex is None:
            return []
        return [PlaceRoad(edge) for edge in setup_road_edges(state, state.setup_vertex)]
    if state.phase == "roll":
        return [Roll()]
    if state.phase == "discard":
        return [
            Discard(resource)
            for resource in RESOURCES
            if hand_get(state.hands[player], resource) > 0
        ]
    if state.phase == "move_robber":
        return robber_actions(state, player, knight=False)
    if state.phase == "free_road":
        return [
            PlaceRoad(edge)
            for edge in legal_free_road_edges(state, player)
            if state.roads[edge] is None
        ]
    if state.phase == "trade_response":
        offer = state.pending_offer
        actions: list[Action] = []
        if (
            offer is not None
            and offer.to_player == player
            and hand_get(state.hands[offer.from_player], offer.give) > 0
            and hand_get(state.hands[player], offer.take) > 0
        ):
            actions.append(AcceptOffer())
        actions.append(DeclineOffer())
        return actions
    if state.phase == "actions":
        return action_phase_actions(state, player)
    return []


def action_phase_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Everything the active player may do after rolling."""
    actions: list[Action] = [EndTurn()]
    hand = state.hands[player]
    for edge in range(len(state.roads)):
        if (
            state.roads[edge] is None
            and road_legal(state, edge, player)
            and can_afford(hand, ROAD_COST)
        ):
            actions.append(PlaceRoad(edge))
    for vertex in range(len(state.buildings)):
        if settlement_legal(state, vertex, player) and can_afford(
            hand, SETTLEMENT_COST
        ):
            actions.append(PlaceSettlement(vertex))
    for vertex in range(len(state.buildings)):
        if city_legal(state, vertex, player) and can_afford(hand, CITY_COST):
            actions.append(BuildCity(vertex))
    if state.dev_deck and can_afford(hand, DEV_COST):
        actions.append(BuyDev())
    rates = trade_rates(state, player)
    for give in RESOURCES:
        rate = rates[give]
        if hand_get(hand, give) < rate:
            continue
        for take in RESOURCES:
            if take != give:
                actions.append(BankTrade(give, rate, take))
    can_offer = (
        state.config.max_offers_per_turn == 0
        or state.offers_this_turn < state.config.max_offers_per_turn
    )
    if can_offer:
        for target in seats(state.config.num_players):
            if target == player:
                continue
            for give in RESOURCES:
                if hand_get(hand, give) < 1:
                    continue
                for take in RESOURCES:
                    if take == give:
                        continue
                    if hand_get(state.hands[target], take) < 1:
                        continue
                    actions.append(OfferTrade(give, take, target))
    if not state.dev_played_this_turn:
        playable = hand_minus(state.dev_hands[player], state.dev_bought) or empty_hand()
        if dev_get(playable, "knight") > 0:
            actions.extend(robber_actions(state, player, knight=True))
        if dev_get(playable, "road_building") > 0 and legal_free_road_edges(
            state, player
        ):
            actions.append(PlayRoadBuilding())
        if dev_get(playable, "year_of_plenty") > 0:
            for first_index, first in enumerate(RESOURCES):
                for second in RESOURCES[first_index:]:
                    actions.append(PlayYearOfPlenty(first, second))
        if dev_get(playable, "monopoly") > 0:
            actions.extend(PlayMonopoly(resource) for resource in RESOURCES)
    return actions


def robber_actions(
    state: CatanState, player: PlayerId, *, knight: bool
) -> list[Action]:
    """Move-robber choices: every other hex, with each eligible victim."""
    actions: list[Action] = []
    for hex_id in range(len(state.hexes)):
        if hex_id == state.robber:
            continue
        victims = robber_victims(state, hex_id, player)
        if victims:
            for victim in victims:
                actions.append(
                    PlayKnight(hex_id, victim) if knight else MoveRobber(hex_id, victim)
                )
        else:
            actions.append(
                PlayKnight(hex_id, None) if knight else MoveRobber(hex_id, None)
            )
    return actions


def setup_road_edges(state: CatanState, vertex: int) -> tuple[int, ...]:
    """Empty paths touching the settlement just placed."""
    return tuple(
        edge for edge in VERTEX_EDGES[vertex] if setup_road_legal(state, edge, vertex)
    )


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


def pay_cost(state: CatanState, player: PlayerId, cost: Hand) -> CatanState:
    """Subtract a cost from a player's hand or raise."""
    hand = hand_minus(state.hands[player], cost)
    if hand is None:
        raise IllegalActionError("you do not have the cards for that build")
    return replace(state, hands=replace_at(state.hands, player, hand))


def move_robber_and_steal(
    state: CatanState,
    player: PlayerId,
    hex_id: int,
    victim: PlayerId | None,
) -> tuple[CatanState, list[Event]]:
    """Move the robber and take one random card from an eligible victim."""
    events = [
        Event(
            "robber_moved",
            f"{seat_label(player)} moved the robber to {hex_name(state, hex_id)}.",
            {"player": player, "hex": hex_id, "victim": victim},
        )
    ]
    moved = replace(state, robber=hex_id)
    if victim is None:
        return moved, events
    cards = hand_cards(moved.hands[victim])
    if not cards:
        return moved, events
    index, rng = moved.rng.below(len(cards))
    resource = cards[index]
    robbed = replace_at(
        moved.hands, victim, hand_with(moved.hands[victim], resource, -1)
    )
    hands = replace_at(robbed, player, hand_with(robbed[player], resource, 1))
    events.extend(
        [
            Event(
                "stolen",
                f"{seat_label(player)} stole a card from {seat_label(victim)}.",
                {"player": player, "victim": victim},
            ),
            Event(
                "stole_card",
                f"You stole 1 {resource} from {seat_label(victim)}.",
                {"player": player, "from": victim, "resource": resource},
                audience=frozenset({player}),
            ),
            Event(
                "card_stolen",
                f"{seat_label(player)} stole 1 {resource} from you.",
                {"player": player, "from": victim, "resource": resource},
                audience=frozenset({victim}),
            ),
        ]
    )
    return replace(moved, rng=rng, hands=hands), events


def production_event(gains: tuple[Hand, ...], total: int) -> Event:
    """Public summary of resources produced by a roll."""
    parts: list[str] = []
    for player, gain in enumerate(gains):
        cards = [
            f"{count} {resource}"
            for resource, count in zip(RESOURCES, gain, strict=True)
            if count
        ]
        if cards:
            parts.append(f"{seat_label(PlayerId(player))} {', '.join(cards)}")
    text = (
        f"Production on {total}: " + "; ".join(parts) + "."
        if parts
        else f"No resources are produced on {total}."
    )
    return Event(
        "production",
        text,
        {"total": total, "gains": [hand_json(gain) for gain in gains]},
    )


def update_longest_road(
    state: CatanState,
) -> tuple[CatanState, list[Event]]:
    """Recompute the longest road award after a road or building changes."""
    lengths = longest_road_lengths(state)
    best = max(lengths)
    current = state.longest_road
    if (
        current is not None
        and lengths[current] >= LONGEST_ROAD_MINIMUM
        and lengths[current] == best
    ):
        holder = current
    elif best >= LONGEST_ROAD_MINIMUM:
        holder = PlayerId(
            min(player for player, length in enumerate(lengths) if length == best)
        )
    else:
        holder = None
    if holder == current:
        return state, []
    events: list[Event] = []
    if current is not None:
        events.append(
            Event(
                "longest_road_lost",
                f"{seat_label(current)} lost the longest road.",
                {"player": current},
            )
        )
    if holder is not None:
        events.append(
            Event(
                "longest_road",
                f"{seat_label(holder)} has the longest road with {best} paths.",
                {"player": holder, "length": best},
            )
        )
    return replace(state, longest_road=holder), events


def update_largest_army(
    state: CatanState,
) -> tuple[CatanState, list[Event]]:
    """Recompute the largest army award after a knight is played."""
    counts = state.knights_played
    best = max(counts)
    current = state.largest_army
    if (
        current is not None
        and counts[current] >= LARGEST_ARMY_MINIMUM
        and counts[current] == best
    ):
        holder = current
    elif best >= LARGEST_ARMY_MINIMUM:
        holder = PlayerId(
            min(player for player, count in enumerate(counts) if count == best)
        )
    else:
        holder = None
    if holder == current:
        return state, []
    events: list[Event] = []
    if current is not None:
        events.append(
            Event(
                "largest_army_lost",
                f"{seat_label(current)} lost the largest army.",
                {"player": current},
            )
        )
    if holder is not None:
        events.append(
            Event(
                "largest_army",
                f"{seat_label(holder)} has the largest army with {best} knights.",
                {"player": holder, "knights": best},
            )
        )
    return replace(state, largest_army=holder), events


def finish_if_won(
    state: CatanState, events: tuple[Event, ...]
) -> Transition[CatanState]:
    """End the game as soon as any player reaches the victory-point target."""
    players = seats(state.config.num_players)
    points = {player: total_points(state, player) for player in players}
    best = max(points.values())
    if best < state.config.victory_points:
        return Transition(state, events)
    winners = [player for player in players if points[player] == best]
    winner = state.active if state.active in winners else winners[0]
    scores: list[JsonValue] = [
        {
            "player": player,
            "points": points[player],
            "breakdown": point_breakdown(state, player, include_hidden=True),
        }
        for player in players
    ]
    return Transition(
        replace(
            state,
            phase="game_over",
            winner=winner,
            pending_offer=None,
            free_roads=0,
        ),
        (
            *events,
            Event(
                "game_over",
                f"{seat_label(winner)} wins with {best:g} victory points.",
                {"winner": winner, "points": best, "scores": scores},
            ),
        ),
    )


def explain_illegal(state: CatanState, player: PlayerId, action: Action) -> str:
    """Why an action is illegal, in terms useful to a retrying LLM."""
    try:
        return explain_illegal_inner(state, player, action)
    except (IndexError, KeyError, TypeError, ValueError):
        try:
            notation = format_action(action)
        except (TypeError, ValueError):
            notation = repr(action)
        return f"{notation!r} is not a legal action now."


def explain_illegal_inner(state: CatanState, player: PlayerId, action: Action) -> str:
    """The detailed branch of `explain_illegal`."""
    hand = state.hands[player]
    match action:
        case Roll():
            if state.phase != "roll":
                return "You can only roll at the start of your turn."
            return "Rolling is not legal now."
        case EndTurn():
            if state.phase != "actions":
                return "You can only end your turn after rolling and acting."
            return "You cannot end your turn now."
        case PlaceSettlement(vertex=vertex):
            return explain_settlement(state, player, hand, vertex)
        case PlaceRoad(edge=edge):
            return explain_road(state, player, hand, edge)
        case BuildCity(vertex=vertex):
            return explain_city(state, player, hand, vertex)
        case BuyDev():
            if not state.dev_deck:
                return "The development-card deck is empty."
            if not can_afford(hand, DEV_COST):
                return (
                    f"You lack {missing_text(hand, DEV_COST)} for a development card."
                )
            return "You cannot buy a development card now."
        case Discard(resource=resource):
            if state.phase != "discard":
                return "You only discard after a 7."
            if hand_get(hand, resource) < 1:
                return f"You have no {resource} to discard."
            return "You cannot discard that card now."
        case MoveRobber(hex=hex_id, victim=victim):
            return explain_robber(state, player, hex_id, victim, knight=False)
        case PlayKnight(hex=hex_id, victim=victim):
            return explain_robber(state, player, hex_id, victim, knight=True)
        case BankTrade(give=give, give_count=count, take=take):
            if give == take:
                return "A bank trade must exchange two different resources."
            rate = trade_rates(state, player)[give]
            if count != rate:
                return f"Your bank rate for {give} is {rate}:1, not {count}:1."
            if hand_get(hand, give) < rate:
                return f"You need {rate} {give} for that trade."
            return "You cannot make that bank trade now."
        case OfferTrade(give=give, take=take, target=target):
            if (
                state.config.max_offers_per_turn
                and state.offers_this_turn >= state.config.max_offers_per_turn
            ):
                limit = state.config.max_offers_per_turn
                noun = "offer" if limit == 1 else "offers"
                return f"You have already made {limit} {noun} this turn."
            if target == player:
                return "You cannot offer a trade to yourself."
            if not 0 <= target < state.config.num_players:
                return f"There is no {seat_label(target)}."
            if hand_get(hand, give) < 1:
                return f"You have no {give} to offer."
            if hand_get(state.hands[target], take) < 1:
                return f"{seat_label(target)} has no {take} to trade."
            return "You cannot offer that trade now."
        case AcceptOffer():
            if state.pending_offer is None:
                return "There is no open offer to accept."
            return "That offer is not yours to accept."
        case DeclineOffer():
            if state.pending_offer is None:
                return "There is no open offer to decline."
            return "That offer is not yours to decline."
        case PlayRoadBuilding():
            if state.dev_played_this_turn:
                return "You may play only one development card per turn."
            if (
                dev_get(
                    hand_minus(state.dev_hands[player], state.dev_bought)
                    or empty_hand(),
                    "road_building",
                )
                < 1
            ):
                return "You have no playable Road Building card."
            return "You cannot play Road Building now."
        case PlayYearOfPlenty(first=first, second=second):
            if state.dev_played_this_turn:
                return "You may play only one development card per turn."
            if (
                dev_get(
                    hand_minus(state.dev_hands[player], state.dev_bought)
                    or empty_hand(),
                    "year_of_plenty",
                )
                < 1
            ):
                return "You have no playable Year of Plenty card."
            return f"You cannot play Year of Plenty for {first} and {second} now."
        case PlayMonopoly(resource=resource):
            if state.dev_played_this_turn:
                return "You may play only one development card per turn."
            if (
                dev_get(
                    hand_minus(state.dev_hands[player], state.dev_bought)
                    or empty_hand(),
                    "monopoly",
                )
                < 1
            ):
                return "You have no playable Monopoly card."
            return f"You cannot play Monopoly on {resource} now."
    return f"{format_action(action)!r} is not a legal action now."


def explain_settlement(
    state: CatanState, player: PlayerId, hand: Hand, vertex: int
) -> str:
    """Why a settlement placement is illegal."""
    if not 0 <= vertex < len(state.buildings):
        return f"v{vertex} is not on the board."
    building = state.buildings[vertex]
    if building is not None:
        return f"v{vertex} already has a {building.kind}."
    if not distance_rule_ok(state, vertex):
        return f"v{vertex} is adjacent to another building."
    if state.phase == "setup_settlement":
        return "That intersection is not available during setup."
    if not settlement_connected(state, vertex, player):
        return f"A settlement on v{vertex} must touch one of your roads."
    if not settlement_pieces_available(state, player):
        return "You have no settlement pieces left."
    if not can_afford(hand, SETTLEMENT_COST):
        return f"You lack {missing_text(hand, SETTLEMENT_COST)} for a settlement."
    return "You cannot place a settlement now."


def explain_road(state: CatanState, player: PlayerId, hand: Hand, edge: int) -> str:
    """Why a road placement is illegal."""
    if not 0 <= edge < len(state.roads):
        return f"e{edge} is not on the board."
    if state.roads[edge] is not None:
        return f"e{edge} already has a road."
    if state.phase == "setup_road":
        if state.setup_vertex is None:
            return "Place a settlement first."
        return f"Your setup road must touch v{state.setup_vertex}."
    if not road_legal(state, edge, player):
        return f"e{edge} does not connect to your network or you have no roads left."
    if state.phase == "actions" and not can_afford(hand, ROAD_COST):
        return f"You lack {missing_text(hand, ROAD_COST)} for a road."
    return "You cannot place a road now."


def explain_city(state: CatanState, player: PlayerId, hand: Hand, vertex: int) -> str:
    """Why a city upgrade is illegal."""
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
    if not can_afford(hand, CITY_COST):
        return f"You lack {missing_text(hand, CITY_COST)} for a city."
    return "You cannot build a city now."


def explain_robber(
    state: CatanState,
    player: PlayerId,
    hex_id: int,
    victim: PlayerId | None,
    *,
    knight: bool,
) -> str:
    """Why a robber move or knight play is illegal."""
    label = "knight" if knight else "robber"
    if knight and state.dev_played_this_turn:
        return "You may play only one development card per turn."
    if (
        knight
        and dev_get(
            hand_minus(state.dev_hands[player], state.dev_bought) or empty_hand(),
            "knight",
        )
        < 1
    ):
        return "You have no playable knight card."
    if not knight and state.phase != "move_robber":
        return "You can only move the robber after rolling a 7."
    if not 0 <= hex_id < len(state.hexes):
        return f"h{hex_id} is not on the board."
    if hex_id == state.robber:
        return "The robber is already on that hex; choose a different hex."
    if victim == player:
        return "You cannot steal from yourself."
    victims = robber_victims(state, hex_id, player)
    if victims and victim is None:
        return "You must steal from an eligible player on that hex."
    if victim is not None and victim not in victims:
        return f"{seat_label(victim)} has no building or cards on h{hex_id}."
    if not victims and victim is not None:
        return f"No player on h{hex_id} has a card to steal."
    return f"You cannot move the {label} there now."


def missing_text(hand: Hand, cost: Hand) -> str:
    """ "2 wood, 1 ore" for the cards a hand lacks toward a cost."""
    parts = [
        f"{need - have} {resource}"
        for resource, have, need in zip(RESOURCES, hand, cost, strict=True)
        if have < need
    ]
    return ", ".join(parts) or "nothing"


def hex_name(state: CatanState, hex_id: int) -> str:
    """ "h5 forest 6" for event text."""
    board_hex = state.hexes[hex_id]
    number = "" if board_hex.number is None else f" {board_hex.number}"
    return f"h{hex_id} {board_hex.terrain}{number}"


def dev_name(card: DevCard) -> str:
    """Human name of a development card."""
    return card.replace("_", " ")


def replace_at[T](items: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    """A tuple with one item replaced."""
    return (*items[:index], value, *items[index + 1 :])


def board_summary(state: CatanState) -> str:
    """One-line board summary used by tests and debugging output."""
    counts = {
        terrain: sum(1 for board_hex in state.hexes if board_hex.terrain == terrain)
        for terrain in {board_hex.terrain for board_hex in state.hexes}
    }
    parts = ", ".join(f"{terrain} {count}" for terrain, count in sorted(counts.items()))
    return f"{parts}; robber {hex_name(state, state.robber)}"
