"""Catan turn flow: the roll, discards after a 7, the robber and the end of turn."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.catan.model import (
    DISCARD_THRESHOLD,
    RESOURCES,
    Action,
    CatanState,
    Discard,
    Hand,
    MoveRobber,
    Phase,
    PlayKnight,
    Resource,
    dev_get,
    empty_dev_hand,
    hand_cards,
    hand_get,
    hand_json,
    hand_plus,
    hand_total,
    hand_with,
    playable_dev_hand,
    replace_at,
)
from boardgames.games.catan.rules import production, robber_victims


def explain_roll(state: CatanState) -> str:
    """Why rolling is illegal."""
    if state.phase != "roll":
        return "You can only roll at the start of your turn."
    return "Rolling is not legal now."


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


def roll_dice(state: CatanState, player: PlayerId) -> Transition[CatanState]:
    """Roll two dice: a 7 starts discards and the robber, any other total produces."""
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


def discard_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """One discard per resource the player still holds."""
    return [
        Discard(resource)
        for resource in RESOURCES
        if hand_get(state.hands[player], resource) > 0
    ]


def explain_discard(state: CatanState, hand: Hand, resource: Resource) -> str:
    """Why a discard is illegal."""
    if state.phase != "discard":
        return "You only discard after a 7."
    if hand_get(hand, resource) < 1:
        return f"You have no {resource} to discard."
    return "You cannot discard that card now."


def discard_card(
    state: CatanState, player: PlayerId, resource: Resource
) -> Transition[CatanState]:
    """Discard one card; the robber moves once every discard is made."""
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
    if knight and dev_get(playable_dev_hand(state, player), "knight") < 1:
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
        return f"{seat_label(victim)} has no building on h{hex_id}."
    if not victims and victim is not None:
        return f"No player on h{hex_id} has a building to rob."
    return f"You cannot move the {label} there now."


def hex_name(state: CatanState, hex_id: int) -> str:
    """ "h5 forest 6" for event text."""
    board_hex = state.hexes[hex_id]
    number = "" if board_hex.number is None else f" {board_hex.number}"
    return f"h{hex_id} {board_hex.terrain}{number}"


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


def move_robber(
    state: CatanState,
    player: PlayerId,
    hex_id: int,
    victim: PlayerId | None,
) -> Transition[CatanState]:
    """Move the robber after a 7, then return to the action phase."""
    moved, events = move_robber_and_steal(state, player, hex_id, victim)
    return Transition(replace(moved, phase="actions"), tuple(events))


def explain_end_turn(state: CatanState) -> str:
    """Why ending the turn is illegal."""
    if state.phase != "actions":
        return "You can only end your turn after rolling and acting."
    return "You cannot end your turn now."


def end_turn(state: CatanState, player: PlayerId) -> Transition[CatanState]:
    """Pass the turn clockwise and clear the per-turn counters."""
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
            dev_bought=empty_dev_hand(),
            dev_played_this_turn=False,
            pending_offer=None,
            discard_remaining=(0,) * state.config.num_players,
        ),
        tuple(events),
    )
