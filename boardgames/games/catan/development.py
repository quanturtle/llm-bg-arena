"""Catan development cards: buying from the deck and playing the action cards."""

from dataclasses import replace

from boardgames.core import Event, PlayerId, Transition, seat_label, seats
from boardgames.games.catan.awards import finish_if_won, update_largest_army
from boardgames.games.catan.building import missing_text, pay_cost
from boardgames.games.catan.model import (
    DEV_COST,
    RESOURCES,
    Action,
    BuyDev,
    CatanState,
    DevCard,
    Hand,
    Phase,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
    Resource,
    can_afford,
    dev_get,
    dev_with,
    hand_get,
    hand_with,
    playable_dev_hand,
    replace_at,
)
from boardgames.games.catan.rules import legal_free_road_edges
from boardgames.games.catan.turn import move_robber_and_steal, robber_actions


def dev_purchase_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Buying the top card, when the deck has one and the player can pay."""
    if state.dev_deck and can_afford(state.hands[player], DEV_COST):
        return [BuyDev()]
    return []


def explain_dev_purchase(state: CatanState, hand: Hand) -> str:
    """Why buying a development card is illegal."""
    if not state.dev_deck:
        return "The development-card deck is empty."
    if not can_afford(hand, DEV_COST):
        return f"You lack {missing_text(hand, DEV_COST)} for a development card."
    return "You cannot buy a development card now."


def dev_name(card: DevCard) -> str:
    """Human name of a development card, as event texts spell it."""
    return card.replace("_", " ")


def buy_dev(state: CatanState, player: PlayerId) -> Transition[CatanState]:
    """Pay for the top card of the deck; only its buyer learns what it is."""
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


def dev_play_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Cards held since before this turn, while no card has been played this turn."""
    actions: list[Action] = []
    if not state.dev_played_this_turn:
        playable = playable_dev_hand(state, player)
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


def play_knight(
    state: CatanState,
    player: PlayerId,
    hex_id: int,
    victim: PlayerId | None,
) -> Transition[CatanState]:
    """Move the robber and steal, then recount the largest army."""
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


def explain_road_building(state: CatanState, player: PlayerId) -> str:
    """Why playing Road Building is illegal."""
    if state.dev_played_this_turn:
        return "You may play only one development card per turn."
    if dev_get(playable_dev_hand(state, player), "road_building") < 1:
        return "You have no playable Road Building card."
    return "You cannot play Road Building now."


def play_road_building(state: CatanState, player: PlayerId) -> Transition[CatanState]:
    """Grant two free roads, placed next in the free_road phase."""
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
    phase: Phase = "free_road" if legal_free_road_edges(prepared, player) else "actions"
    return Transition(replace(prepared, phase=phase), tuple(events))


def explain_year_of_plenty(
    state: CatanState, player: PlayerId, first: Resource, second: Resource
) -> str:
    """Why playing Year of Plenty is illegal."""
    if state.dev_played_this_turn:
        return "You may play only one development card per turn."
    if dev_get(playable_dev_hand(state, player), "year_of_plenty") < 1:
        return "You have no playable Year of Plenty card."
    return f"You cannot play Year of Plenty for {first} and {second} now."


def play_year_of_plenty(
    state: CatanState,
    player: PlayerId,
    first: Resource,
    second: Resource,
) -> Transition[CatanState]:
    """Take two resource cards from the bank."""
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


def explain_monopoly(state: CatanState, player: PlayerId, resource: Resource) -> str:
    """Why playing Monopoly is illegal."""
    if state.dev_played_this_turn:
        return "You may play only one development card per turn."
    if dev_get(playable_dev_hand(state, player), "monopoly") < 1:
        return "You have no playable Monopoly card."
    return f"You cannot play Monopoly on {resource} now."


def play_monopoly(
    state: CatanState, player: PlayerId, resource: Resource
) -> Transition[CatanState]:
    """Take every card of one resource from the other players."""
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
