"""The Puerto Rico Builder: buying a building and the University colonist."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.model import (
    Action,
    Build,
    OwnedBuilding,
    Pass,
    PuertoRicoState,
    available_to_build,
    build_cost,
    replace_player,
)
from boardgames.games.puerto_rico.roles.mayor import can_take_colonist, take_colonist
from boardgames.games.puerto_rico.rounds import mark_acted


def apply_builder(
    state: PuertoRicoState, player: PlayerId, action: Action
) -> Transition[PuertoRicoState]:
    if isinstance(action, Build):
        name = action.building
        cost = build_cost(state, player, name)
        owner = state.players[player]
        state = replace_player(
            state,
            player,
            replace(
                owner,
                doubloons=owner.doubloons - cost,
                buildings=(*owner.buildings, OwnedBuilding(name)),
            ),
        )
        available = list(state.available_buildings)
        available.remove(name)
        state = replace(state, available_buildings=tuple(available))
        events = [
            Event(
                "building_built",
                f"{seat_label(player)} built {name} for {cost} doubloons.",
                {"player": player, "building": name, "cost": cost},
            )
        ]
        if owner.active("university") and action.use_university:
            state, colonized = take_colonist(state)
            if colonized:
                new_buildings = list(state.players[player].buildings)
                index = len(new_buildings) - 1
                new_buildings[index] = replace(new_buildings[index], colonists=1)
                state = replace_player(
                    state,
                    player,
                    replace(state.players[player], buildings=tuple(new_buildings)),
                )
                events.append(
                    Event(
                        "university_colonist",
                        f"The University placed a colonist on {name}.",
                        {"player": player, "building": name},
                    )
                )
        state, advanced = mark_acted(state, player)
        return Transition(state, (*events, *advanced))
    if isinstance(action, Pass):
        state, advanced = mark_acted(state, player)
        event = Event(
            "builder_passed",
            f"{seat_label(player)} built nothing.",
            {"player": player},
        )
        return Transition(state, (event, *advanced))
    raise IllegalActionError("only build or pass actions are legal")


def builder_actions(state: PuertoRicoState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    university = owner.active("university") and can_take_colonist(state)
    actions: list[Action] = []
    for name in available_to_build(state, player):
        actions.append(Build(name))
        if university:
            actions.append(Build(name, use_university=False))
    actions.append(Pass())
    return actions


def explain_builder(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a Builder action is not legal for `player` now."""
    owner = state.players[player]
    if isinstance(action, Build) and action.building not in available_to_build(
        state, player
    ):
        return "You cannot afford that building or have no room."
    if isinstance(action, Build) and not action.use_university:
        if not owner.active("university"):
            return "You have no active University."
        if not can_take_colonist(state):
            return "There is no colonist available to place."
    return "Build an available building or pass."
