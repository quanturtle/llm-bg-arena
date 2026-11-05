"""Puerto Rico role selection: taking a role and starting its action phase."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import Role
from boardgames.games.puerto_rico.model import (
    Action,
    Phase,
    PuertoRicoState,
    SelectRole,
    replace_player,
    replace_role,
    role_state,
)
from boardgames.games.puerto_rico.roles.craftsman import run_production
from boardgames.games.puerto_rico.roles.mayor import distribute_colonists
from boardgames.games.puerto_rico.rounds import advance_role_picker

ROLE_PHASE: dict[Role, Phase] = {
    "settler": "settler_action",
    "mayor": "mayor_action",
    "builder": "builder_action",
    "craftsman": "craftsman_action",
    "trader": "trader_action",
    "captain": "captain_action",
}


def start_role_phase(
    state: PuertoRicoState, role: Role, player: PlayerId
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    phase = ROLE_PHASE[role]
    state = replace(
        state,
        active_role=role,
        phase=phase,
        active_player=player,
        players_acted=frozenset(),
        captain_passes=0,
    )
    events: list[Event] = []
    if role == "settler":
        state = replace(
            state,
            players=tuple(replace(item, hacienda_used=False) for item in state.players),
        )
    elif role == "mayor":
        has_extra = state.colonist_supply > 0
        state = distribute_colonists(state, player)
        events.append(
            Event(
                "colonists_distributed",
                "Colonists from the ship are distributed; "
                + (
                    f"{seat_label(player)} takes the extra colonist."
                    if has_extra
                    else "the supply is empty, so there is no extra colonist."
                ),
                {"player": player},
            )
        )
    elif role == "craftsman":
        state, produced_events = run_production(state, player)
        events.extend(produced_events)
    elif role == "captain":
        state = replace(
            state,
            players=tuple(
                replace(
                    item,
                    captain_first_load_done=False,
                    wharf_used=False,
                )
                for item in state.players
            ),
        )
    return state, tuple(events)


def take_role(
    state: PuertoRicoState, player: PlayerId, role: Role
) -> Transition[PuertoRicoState]:
    role_entry = role_state(state, role)
    owner = state.players[player]
    owner = replace(owner, doubloons=owner.doubloons + role_entry.doubloons)
    state = replace_player(state, player, owner)
    state = replace_role(state, role, replace(role_entry, doubloons=0, taken_by=player))
    events = [
        Event(
            "role_taken",
            f"{seat_label(player)} chose {role} (+{role_entry.doubloons} doubloons).",
            {
                "player": player,
                "role": role,
                "doubloons": role_entry.doubloons,
            },
        )
    ]
    if role in ("prospector", "prospector_2"):
        owner = replace(
            state.players[player], doubloons=state.players[player].doubloons + 1
        )
        state = replace_player(state, player, owner)
        events.append(
            Event(
                "prospector_bonus",
                f"{seat_label(player)} took a prospector: +1 doubloon.",
                {"player": player, "doubloons": 1},
            )
        )
        state = advance_role_picker(state)
        return Transition(state, tuple(events))
    state, phase_events = start_role_phase(state, role, player)
    events.extend(phase_events)
    return Transition(state, tuple(events))


def apply_selection(
    state: PuertoRicoState, player: PlayerId, action: Action
) -> Transition[PuertoRicoState]:
    """Take the chosen role; nothing but a role choice is legal now."""
    if not isinstance(action, SelectRole):
        raise IllegalActionError("choose a role now")
    return take_role(state, player, action.role)


def select_role_reason(state: PuertoRicoState, role: Role) -> str | None:
    """Why `role` cannot be chosen now; None when it can."""
    entry = next((item for item in state.roles if item.role == role), None)
    if entry is None:
        return f"There is no {role} role in this game."
    if entry.taken_by is not None:
        return f"{role} was already chosen this round."
    return None


def selection_actions(state: PuertoRicoState) -> list[Action]:
    """Every role nobody has taken this round."""
    return [
        SelectRole(entry.role)
        for entry in state.roles
        if select_role_reason(state, entry.role) is None
    ]


def explain_selection(state: PuertoRicoState, action: Action) -> str:
    """Why a role choice is not legal now."""
    reason = None
    if isinstance(action, SelectRole):
        reason = select_role_reason(state, action.role)
    return reason or "Choose a role that nobody has taken this round."
