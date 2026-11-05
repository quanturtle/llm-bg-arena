"""Catan: the standard 19-hex base game for 3 or 4 players.

The board is fixed geometry; terrain, number tokens, ports and the development
deck are shuffled from the match seed. Hidden information is each player's
resource hand and development cards. A move is a small notation such as
`settle v12`, `road e34`, `bank 4 wood for 1 ore` or `end turn`.
"""

from functools import partial
from importlib.resources import files
from typing import ClassVar

from boardgames.core import (
    Decision,
    FlatActionSpace,
    IllegalActionError,
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    Scores,
    Transition,
    checked_apply,
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
from boardgames.games.catan.building import (
    build_actions,
    build_city,
    build_road,
    build_settlement,
    explain_city,
    explain_road,
    explain_settlement,
    free_road_actions,
    place_free_road,
)
from boardgames.games.catan.development import (
    buy_dev,
    dev_play_actions,
    dev_purchase_actions,
    explain_dev_purchase,
    explain_monopoly,
    explain_road_building,
    explain_year_of_plenty,
    play_knight,
    play_monopoly,
    play_road_building,
    play_year_of_plenty,
)
from boardgames.games.catan.model import (
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    BuyDev,
    CatanConfig,
    CatanState,
    DeclineOffer,
    Discard,
    EndTurn,
    MoveRobber,
    OfferTrade,
    Phase,
    PlaceRoad,
    PlaceSettlement,
    PlayKnight,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
    Roll,
    point_breakdown,
)
from boardgames.games.catan.notation import format_action, parse_action
from boardgames.games.catan.setup import (
    check_config,
    place_setup_road,
    place_setup_settlement,
    setup_road_actions,
    setup_settlement_actions,
    start_game,
)
from boardgames.games.catan.trading import (
    accept_offer,
    bank_trade,
    bank_trade_actions,
    decline_offer,
    explain_accept,
    explain_bank_trade,
    explain_decline,
    explain_offer,
    offer_actions,
    offer_trade,
    response_actions,
)
from boardgames.games.catan.turn import (
    discard_actions,
    discard_card,
    end_turn,
    explain_discard,
    explain_end_turn,
    explain_robber,
    explain_roll,
    move_robber,
    robber_actions,
    roll_dice,
)
from boardgames.games.catan.view import (
    describe_action,
    observe,
    render_text,
)


@register_game
class Catan:
    """Standard Catan with settlements, cities, roads, trade and development cards."""

    id: ClassVar[str] = "catan"
    rules_version: ClassVar[int] = 2

    def parse_config(self, raw: JsonObject) -> CatanConfig:
        config = dataclass_from_json(CatanConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: CatanConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    def setup(self, config: CatanConfig, seed: int) -> Transition[CatanState]:
        return start_game(config, seed)

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
        return checked_apply(
            self,
            state,
            player,
            action,
            no_decision=(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            ),
        )

    def apply_legal(
        self, state: CatanState, player: PlayerId, action: Action
    ) -> Transition[CatanState]:
        """Apply an action already checked by `legal_actions`."""
        if state.phase == "setup_settlement":
            if not isinstance(action, PlaceSettlement):
                raise IllegalActionError("only a settlement is legal during setup")
            return place_setup_settlement(state, player, action.vertex)
        if state.phase == "setup_road":
            if not isinstance(action, PlaceRoad):
                raise IllegalActionError("only a road is legal during setup")
            return place_setup_road(state, player, action.edge)
        if state.phase == "roll":
            return roll_dice(state, player)
        if state.phase == "discard":
            if not isinstance(action, Discard):
                raise IllegalActionError("only discards are legal now")
            return discard_card(state, player, action.resource)
        if state.phase == "move_robber":
            if not isinstance(action, MoveRobber):
                raise IllegalActionError("move the robber now")
            return move_robber(state, player, action.hex, action.victim)
        if state.phase == "free_road":
            if not isinstance(action, PlaceRoad):
                raise IllegalActionError("place a free road now")
            return place_free_road(state, player, action.edge)
        if state.phase == "trade_response":
            if isinstance(action, AcceptOffer):
                return accept_offer(state, player)
            if isinstance(action, DeclineOffer):
                return decline_offer(state, player)
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

    def public_scores(self, state: CatanState) -> Scores:
        """Victory point cards stay hidden until the game ends and reveals them."""
        if self.is_terminal(state):
            return self.scores(state)
        breakdown = {
            player: point_breakdown(state, player, include_hidden=False)
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

    def apply_action_phase(
        self, state: CatanState, player: PlayerId, action: Action
    ) -> Transition[CatanState]:
        if isinstance(action, PlaceRoad):
            return build_road(state, player, action.edge)
        if isinstance(action, PlaceSettlement):
            return build_settlement(state, player, action.vertex)
        if isinstance(action, BuildCity):
            return build_city(state, player, action.vertex)
        if isinstance(action, BuyDev):
            return buy_dev(state, player)
        if isinstance(action, BankTrade):
            return bank_trade(state, player, action)
        if isinstance(action, OfferTrade):
            return offer_trade(state, player, action)
        if isinstance(action, PlayKnight):
            return play_knight(state, player, action.hex, action.victim)
        if isinstance(action, PlayRoadBuilding):
            return play_road_building(state, player)
        if isinstance(action, PlayYearOfPlenty):
            return play_year_of_plenty(state, player, action.first, action.second)
        if isinstance(action, PlayMonopoly):
            return play_monopoly(state, player, action.resource)
        if isinstance(action, EndTurn):
            return end_turn(state, player)
        raise IllegalActionError("that action is not available in the action phase")


def decision_kind(phase: Phase) -> str:
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
    """The safe action for this phase, if any."""
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
        return setup_settlement_actions(state)
    if state.phase == "setup_road":
        return setup_road_actions(state)
    if state.phase == "roll":
        return [Roll()]
    if state.phase == "discard":
        return discard_actions(state, player)
    if state.phase == "move_robber":
        return robber_actions(state, player, knight=False)
    if state.phase == "free_road":
        return free_road_actions(state, player)
    if state.phase == "trade_response":
        return response_actions(state, player)
    if state.phase == "actions":
        return action_phase_actions(state, player)
    return []


def action_phase_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Everything the active player may do after rolling."""
    actions: list[Action] = [EndTurn()]
    actions.extend(build_actions(state, player))
    actions.extend(dev_purchase_actions(state, player))
    actions.extend(bank_trade_actions(state, player))
    actions.extend(offer_actions(state, player))
    actions.extend(dev_play_actions(state, player))
    return actions


def explain_illegal(state: CatanState, player: PlayerId, action: Action) -> str:
    """Why an action is illegal, in terms useful to a retrying LLM."""
    hand = state.hands[player]
    match action:
        case Roll():
            return explain_roll(state)
        case EndTurn():
            return explain_end_turn(state)
        case PlaceSettlement(vertex=vertex):
            return explain_settlement(state, player, hand, vertex)
        case PlaceRoad(edge=edge):
            return explain_road(state, player, hand, edge)
        case BuildCity(vertex=vertex):
            return explain_city(state, player, hand, vertex)
        case BuyDev():
            return explain_dev_purchase(state, hand)
        case Discard(resource=resource):
            return explain_discard(state, hand, resource)
        case MoveRobber(hex=hex_id, victim=victim):
            return explain_robber(state, player, hex_id, victim, knight=False)
        case PlayKnight(hex=hex_id, victim=victim):
            return explain_robber(state, player, hex_id, victim, knight=True)
        case BankTrade(give=give, give_count=count, take=take):
            return explain_bank_trade(state, player, hand, give, count, take)
        case OfferTrade(give=give, target=target):
            return explain_offer(state, player, hand, give, target)
        case AcceptOffer():
            return explain_accept(state, player, hand)
        case DeclineOffer():
            return explain_decline(state)
        case PlayRoadBuilding():
            return explain_road_building(state, player)
        case PlayYearOfPlenty(first=first, second=second):
            return explain_year_of_plenty(state, player, first, second)
        case PlayMonopoly(resource=resource):
            return explain_monopoly(state, player, resource)
    return f"{format_action(action)!r} is not a legal action now."
