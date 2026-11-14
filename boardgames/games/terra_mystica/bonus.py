"""Terra Mystica bonus cards: income, pass scoring and card choice."""

from boardgames.core import IllegalActionError, PlayerId, seat_label
from boardgames.games.terra_mystica.constants import (
    BONUS_CARDS,
    BonusCard,
    Income,
)
from boardgames.games.terra_mystica.model import (
    Action,
    PlayerState,
    TakeBonusCard,
    TerraMysticaState,
    building_counts,
)


def bonus_card(player: PlayerState) -> BonusCard | None:
    """The player's bonus card, if any."""
    if player.bonus_card is None:
        return None
    return BONUS_CARDS[player.bonus_card]


def bonus_income(player: PlayerState) -> Income:
    card = bonus_card(player)
    return Income() if card is None else card.income


def bonus_pass_vp(state: TerraMysticaState, player: PlayerId) -> int:
    """Victory points a returning bonus card awards for the player's structures."""
    card = bonus_card(state.players[player])
    if card is None:
        return 0
    counts = building_counts(state.board, player)
    return sum(
        count * points for kind, points in card.pass_vp for count in (counts[kind],)
    )


def effective_shipping(state: TerraMysticaState, player: PlayerId) -> int:
    """Shipping for building and transforming, including a bonus-card bonus."""
    owner = state.players[player]
    if not owner.profile.can_ship:
        return owner.shipping
    card = bonus_card(owner)
    return owner.shipping + (0 if card is None else card.shipping_bonus)


def bonus_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    """Bonus cards the player may take now."""
    return [
        TakeBonusCard(index)
        for index in state.bonus_available
        if index != state.bonus_returned
    ]


def explain_bonus(state: TerraMysticaState, action: Action) -> str:
    if not isinstance(action, TakeBonusCard):
        return "Choose a bonus card."
    if action.index not in state.bonus_available:
        return "That bonus card is not available."
    if action.index == state.bonus_returned:
        return "You may not immediately take the card you just returned."
    return "That bonus card cannot be taken now."


def check_bonus_choice(state: TerraMysticaState, player: PlayerId) -> None:
    if state.phase != "bonus_choice" or not state.pending_bonus:
        raise IllegalActionError("no bonus card is owed now")
    if player != state.active_player:
        raise IllegalActionError(f"it is {seat_label(state.active_player)}'s turn")
