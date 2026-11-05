"""The Puerto Rico Mayor and the colonist moves the other roles share."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import BUILDINGS
from boardgames.games.puerto_rico.model import (
    Action,
    FinishPlacement,
    PickUpColonist,
    PlaceColonist,
    PlayerState,
    PuertoRicoState,
    replace_at,
    replace_player,
)
from boardgames.games.puerto_rico.rounds import mark_acted


def can_take_colonist(state: PuertoRicoState) -> bool:
    """Whether the supply or the ship can provide a bonus colonist."""
    return state.colonist_supply + state.colonist_ship > 0


def take_colonist(state: PuertoRicoState) -> tuple[PuertoRicoState, bool]:
    """Take one colonist from the supply, or from the ship when it is empty."""
    if state.colonist_supply > 0:
        return replace(state, colonist_supply=state.colonist_supply - 1), True
    if state.colonist_ship > 0:
        return replace(state, colonist_ship=state.colonist_ship - 1), True
    return state, False


def distribute_colonists(state: PuertoRicoState, picker: PlayerId) -> PuertoRicoState:
    """Round-robin the ship's colonists from the picker; the picker gets +1."""
    n = len(state.order)
    start = state.order.index(picker)
    allocations = [0] * n
    remaining = state.colonist_ship
    index = 0
    while remaining > 0:
        seat = state.order[(start + index) % n]
        allocations[seat] += 1
        remaining -= 1
        index += 1
    players = tuple(
        replace(
            player, colonists_unplaced=player.colonists_unplaced + allocations[seat]
        )
        for seat, player in enumerate(state.players)
    )
    supply = state.colonist_supply
    if supply > 0:
        players = replace_at(
            players,
            picker,
            replace(
                players[picker],
                colonists_unplaced=players[picker].colonists_unplaced + 1,
            ),
        )
        supply -= 1
    return replace(state, players=players, colonist_ship=0, colonist_supply=supply)


def place_colonist(owner: PlayerState, action: PlaceColonist) -> PlayerState:
    """Apply one colonist placement during Mayor."""
    if owner.colonists_unplaced <= 0:
        raise IllegalActionError("no colonists left to place")
    if action.target == "plantation":
        plantation = owner.plantations[action.index]
        if plantation.colonized:
            raise IllegalActionError("that plantation is already colonized")
        return replace(
            owner,
            plantations=replace_at(
                owner.plantations, action.index, replace(plantation, colonized=True)
            ),
            colonists_unplaced=owner.colonists_unplaced - 1,
        )
    if action.target == "building":
        building = owner.buildings[action.index]
        spec = BUILDINGS[building.name]
        if building.colonists >= spec.max_colonists:
            raise IllegalActionError("that building has no empty colonist space")
        return replace(
            owner,
            buildings=replace_at(
                owner.buildings,
                action.index,
                replace(building, colonists=building.colonists + 1),
            ),
            colonists_unplaced=owner.colonists_unplaced - 1,
        )
    if action.target == "quarry":
        if owner.occupied_quarries >= owner.quarries:
            raise IllegalActionError("every quarry already has a colonist")
        return replace(
            owner,
            occupied_quarries=owner.occupied_quarries + 1,
            colonists_unplaced=owner.colonists_unplaced - 1,
        )
    raise IllegalActionError("unknown colonist target")


def colonist_target(action: PlaceColonist | PickUpColonist) -> str:
    if action.target == "quarry":
        return "a quarry"
    return f"{action.target} {action.index}"


def pick_up_colonist(owner: PlayerState, action: PickUpColonist) -> PlayerState:
    """Return one colonist to the unplaced pool during Mayor."""
    if action.target == "plantation":
        plantation = owner.plantations[action.index]
        if not plantation.colonized:
            raise IllegalActionError("that plantation has no colonist")
        return replace(
            owner,
            plantations=replace_at(
                owner.plantations, action.index, replace(plantation, colonized=False)
            ),
            colonists_unplaced=owner.colonists_unplaced + 1,
        )
    if action.target == "building":
        building = owner.buildings[action.index]
        if building.colonists <= 0:
            raise IllegalActionError("that building has no colonist")
        return replace(
            owner,
            buildings=replace_at(
                owner.buildings,
                action.index,
                replace(building, colonists=building.colonists - 1),
            ),
            colonists_unplaced=owner.colonists_unplaced + 1,
        )
    if action.target == "quarry":
        if owner.occupied_quarries <= 0:
            raise IllegalActionError("no quarry has a colonist")
        return replace(
            owner,
            occupied_quarries=owner.occupied_quarries - 1,
            colonists_unplaced=owner.colonists_unplaced + 1,
        )
    raise IllegalActionError("unknown colonist target")


def apply_mayor(
    state: PuertoRicoState, player: PlayerId, action: Action
) -> Transition[PuertoRicoState]:
    owner = state.players[player]
    if isinstance(action, PlaceColonist):
        owner = place_colonist(owner, action)
        state = replace_player(state, player, owner)
        event = Event(
            "colonist_placed",
            f"{seat_label(player)} placed a colonist on {colonist_target(action)}.",
            {"player": player, "target": action.target, "index": action.index},
        )
        return Transition(state, (event,))
    if isinstance(action, PickUpColonist):
        owner = pick_up_colonist(owner, action)
        state = replace_player(state, player, owner)
        event = Event(
            "colonist_picked_up",
            f"{seat_label(player)} picked up a colonist from "
            f"{colonist_target(action)}.",
            {"player": player, "target": action.target, "index": action.index},
        )
        return Transition(state, (event,))
    if isinstance(action, FinishPlacement):
        state, advanced = mark_acted(state, player)
        event = Event(
            "mayor_finished",
            f"{seat_label(player)} finished placing colonists.",
            {"player": player},
        )
        return Transition(state, (event, *advanced))
    raise IllegalActionError("only colonist placements, pickups or finish are legal")


def has_placement_targets(owner: PlayerState) -> bool:
    if owner.colonists_unplaced <= 0:
        return False
    if any(not plantation.colonized for plantation in owner.plantations):
        return True
    if owner.occupied_quarries < owner.quarries:
        return True
    return any(
        building.colonists < BUILDINGS[building.name].max_colonists
        for building in owner.buildings
    )


def mayor_actions(owner: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if owner.colonists_unplaced > 0:
        for index, plantation in enumerate(owner.plantations):
            if not plantation.colonized:
                actions.append(PlaceColonist("plantation", index))
        for index, building in enumerate(owner.buildings):
            spec = BUILDINGS[building.name]
            if building.colonists < spec.max_colonists:
                actions.append(PlaceColonist("building", index))
        if owner.occupied_quarries < owner.quarries:
            actions.append(PlaceColonist("quarry"))
    else:
        # Colonists may be rearranged only after every new colonist is placed;
        # this also keeps a random player from moving the same colonist forever.
        for index, plantation in enumerate(owner.plantations):
            if plantation.colonized:
                actions.append(PickUpColonist("plantation", index))
        for index, building in enumerate(owner.buildings):
            if building.colonists > 0:
                actions.append(PickUpColonist("building", index))
        if owner.occupied_quarries > 0:
            actions.append(PickUpColonist("quarry"))
    if not has_placement_targets(owner):
        actions.append(FinishPlacement())
    return actions


def explain_mayor(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a Mayor action is not legal for `player` now."""
    if isinstance(action, FinishPlacement) and has_placement_targets(
        state.players[player]
    ):
        return "You still have colonists to place."
    if isinstance(action, PlaceColonist | PickUpColonist):
        return "That colonist placement is not available now."
    return "Place or move a colonist, or finish."
