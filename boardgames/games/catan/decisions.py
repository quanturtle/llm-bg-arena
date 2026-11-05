"""Catan decisions: what each phase asks, the legal actions, and why one is illegal.

The listing and the explanations dispatch by phase or action type to the action
families: setup, turn, building, development and trading.
"""

from boardgames.core import PlayerId
from boardgames.games.catan.building import (
    build_actions,
    explain_city,
    explain_road,
    explain_settlement,
    free_road_actions,
)
from boardgames.games.catan.development import (
    dev_play_actions,
    dev_purchase_actions,
    explain_dev_purchase,
    explain_monopoly,
    explain_road_building,
    explain_year_of_plenty,
)
from boardgames.games.catan.model import (
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    BuyDev,
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
)
from boardgames.games.catan.notation import format_action
from boardgames.games.catan.setup import setup_road_actions, setup_settlement_actions
from boardgames.games.catan.trading import (
    bank_trade_actions,
    explain_accept,
    explain_bank_trade,
    explain_decline,
    explain_offer,
    offer_actions,
    response_actions,
)
from boardgames.games.catan.turn import (
    discard_actions,
    explain_discard,
    explain_end_turn,
    explain_robber,
    explain_roll,
    robber_actions,
)


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


def action_phase_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Everything the active player may do after rolling."""
    actions: list[Action] = [EndTurn()]
    actions.extend(build_actions(state, player))
    actions.extend(dev_purchase_actions(state, player))
    actions.extend(bank_trade_actions(state, player))
    actions.extend(offer_actions(state, player))
    actions.extend(dev_play_actions(state, player))
    return actions


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


def default_action(state: CatanState, actions: list[Action]) -> Action | None:
    """The safe action for this phase, if any."""
    if state.phase == "roll":
        return Roll()
    if state.phase == "actions":
        return EndTurn()
    if state.phase == "trade_response":
        return DeclineOffer()
    return None


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
