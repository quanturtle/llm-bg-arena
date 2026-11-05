"""The Puerto Rico Settler: plantations, quarries and the Hacienda draw."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    JsonValue,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import MAX_ISLAND_SPACES, Good
from boardgames.games.puerto_rico.model import (
    Action,
    Pass,
    Plantation,
    PlayerState,
    PuertoRicoState,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
    island_spaces_used,
    replace_player,
    role_chooser,
)
from boardgames.games.puerto_rico.roles.mayor import can_take_colonist, take_colonist
from boardgames.games.puerto_rico.rounds import mark_acted


def apply_settler(
    state: PuertoRicoState, player: PlayerId, action: Action
) -> Transition[PuertoRicoState]:
    owner = state.players[player]
    events: list[Event] = []
    if isinstance(action, UseHacienda):
        if not state.plantation_deck:
            deck, rng = state.rng.shuffled(state.plantation_discard)
            state = replace(
                state,
                plantation_deck=deck,
                plantation_discard=(),
                rng=rng,
            )
            events.append(
                Event(
                    "plantation_discard_reshuffled",
                    "The plantation discard pile was shuffled into a new deck.",
                    {"cards": len(deck)},
                )
            )
        good = state.plantation_deck[0]
        state = replace(
            state,
            plantation_deck=state.plantation_deck[1:],
        )
        state = replace_player(
            state,
            player,
            replace(
                owner,
                plantations=(*owner.plantations, Plantation(good)),
                hacienda_used=True,
            ),
        )
        events.append(
            Event(
                "hacienda_plantation",
                f"{seat_label(player)} drew a {good} plantation.",
                {"player": player, "good": good},
            )
        )
        return Transition(state, tuple(events))
    if isinstance(action, TakePlantation):
        face_up = list(state.face_up)
        face_up.remove(action.good)
        colonized = False
        if owner.active("hospice") and action.use_hospice:
            state, colonized = take_colonist(state)
        state = replace_player(
            state,
            player,
            replace(
                owner,
                plantations=(
                    *owner.plantations,
                    Plantation(action.good, colonized),
                ),
            ),
        )
        state = replace(state, face_up=tuple(face_up))
        event = Event(
            "plantation_taken",
            f"{seat_label(player)} took a {action.good} plantation"
            + (" and colonized it with the Hospice." if colonized else "."),
            {
                "player": player,
                "good": action.good,
                "colonized": colonized,
            },
        )
        state, advanced = mark_acted(state, player)
        return Transition(state, (event, *advanced))
    if isinstance(action, TakeQuarry):
        colonized = False
        if owner.active("hospice") and action.use_hospice:
            state, colonized = take_colonist(state)
        state = replace_player(
            state,
            player,
            replace(
                state.players[player],
                quarries=state.players[player].quarries + 1,
                occupied_quarries=(
                    state.players[player].occupied_quarries + (1 if colonized else 0)
                ),
            ),
        )
        state = replace(state, quarry_supply=state.quarry_supply - 1)
        data: dict[str, JsonValue] = {"player": player}
        if colonized:
            data["colonized"] = True
        event = Event(
            "quarry_taken",
            f"{seat_label(player)} took a quarry"
            + (" and colonized it with the Hospice." if colonized else "."),
            data,
        )
        state, advanced = mark_acted(state, player)
        return Transition(state, (event, *advanced))
    if isinstance(action, Pass):
        state, advanced = mark_acted(state, player)
        event = Event(
            "settler_passed",
            f"{seat_label(player)} took no plantation.",
            {"player": player},
        )
        return Transition(state, (event, *advanced))
    raise IllegalActionError("only plantation, quarry or pass actions are legal")


def can_take_quarry(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> bool:
    """Whether the Settler privilege or a Construction Hut allows a quarry."""
    return role_chooser(state, "settler") == player or owner.active("construction_hut")


def settler_actions(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> list[Action]:
    actions: list[Action] = []
    space = island_spaces_used(owner) < MAX_ISLAND_SPACES
    if (
        space
        and owner.active("hacienda")
        and not owner.hacienda_used
        and (state.plantation_deck or state.plantation_discard)
    ):
        actions.append(UseHacienda())
    if space:
        hospice = owner.active("hospice") and can_take_colonist(state)
        seen: set[Good] = set()
        for good in state.face_up:
            if good not in seen:
                seen.add(good)
                actions.append(TakePlantation(good))
                if hospice:
                    actions.append(TakePlantation(good, use_hospice=False))
        if can_take_quarry(state, player, owner) and state.quarry_supply > 0:
            actions.append(TakeQuarry())
            if hospice:
                actions.append(TakeQuarry(use_hospice=False))
    actions.append(Pass())
    return actions


def explain_settler(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a Settler action is not legal for `player` now."""
    owner = state.players[player]
    if isinstance(action, TakePlantation):
        if action.good not in state.face_up:
            return f"No {action.good} plantation is face up."
        if island_spaces_used(owner) >= MAX_ISLAND_SPACES:
            return "Your island is full."
        if not action.use_hospice:
            if not owner.active("hospice"):
                return "You have no active Hospice."
            if not can_take_colonist(state):
                return "There is no colonist available to place."
    if isinstance(action, TakeQuarry):
        if island_spaces_used(owner) >= MAX_ISLAND_SPACES:
            return "Your island is full."
        if state.quarry_supply <= 0:
            return "No quarries remain."
        if not can_take_quarry(state, player, owner):
            return (
                "You may take a quarry only with the Settler privilege "
                "or a Construction Hut."
            )
        if not action.use_hospice:
            if not owner.active("hospice"):
                return "You have no active Hospice."
            if not can_take_colonist(state):
                return "There is no colonist available to place."
    if isinstance(action, UseHacienda):
        if not owner.active("hacienda"):
            return "You have no active Hacienda."
        if owner.hacienda_used:
            return "Your Hacienda was already used this Settler phase."
        if not state.plantation_deck and not state.plantation_discard:
            return "No plantation remains in the deck or discard pile."
    return "Take a face-up plantation, a quarry if allowed, or pass."
