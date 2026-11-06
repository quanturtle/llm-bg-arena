"""Terra Mystica bridges: the action, valid river crossings and adjacency."""

from dataclasses import replace

from boardgames.core import Event, IllegalActionError, PlayerId, Transition, seat_label
from boardgames.games.terra_mystica.constants import (
    POWER_ACTION_COSTS,
    FactionType,
)
from boardgames.games.terra_mystica.model import (
    Action,
    Board,
    Bridge,
    BuildBridge,
    Hex,
    TerraMysticaState,
    burn_power,
    can_spend_power,
    power_shortfall,
    replace_player,
    spend_power,
)
from boardgames.games.terra_mystica.rounds import advance_turn
from boardgames.games.terra_mystica.towns import town_rewards, town_tile_actions

BRIDGE_SUPPLY = 3
ENGINEER_BRIDGE_COST = 2


def bridge_pairs(board: Board) -> tuple[tuple[Hex, Hex], ...]:
    """Land pairs a bridge can join: two steps apart with a river between."""
    pairs: set[tuple[Hex, Hex]] = set()
    land = [tile.position for tile in board.tiles if tile.is_land]
    for index, first in enumerate(land):
        for second in land[index + 1 :]:
            if first.distance(second) != 2:
                continue
            common = set(first.neighbours()) & set(second.neighbours())
            if any(
                (tile := board.tile(position)) is not None and not tile.is_land
                for position in common
            ):
                pairs.add((first, second) if first < second else (second, first))
    return tuple(sorted(pairs))


def _bridge_count(state: TerraMysticaState, player: PlayerId) -> int:
    return sum(1 for bridge in state.bridges if bridge.owner == player)


def _has_building(state: TerraMysticaState, player: PlayerId, position: Hex) -> bool:
    tile = state.board.tile(position)
    return (
        tile is not None and tile.building is not None and tile.building.owner == player
    )


def bridge_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    """Every legal bridge and payment for the player."""
    owner = state.players[player]
    if _bridge_count(state, player) >= BRIDGE_SUPPLY:
        return []
    taken = {frozenset((bridge.first, bridge.second)) for bridge in state.bridges}
    power_ok = "bridge" not in state.used_power_actions and can_spend_power(
        owner.resources, POWER_ACTION_COSTS["bridge"]
    )
    workers_ok = (
        owner.profile.type is FactionType.ENGINEERS
        and owner.resources.workers >= ENGINEER_BRIDGE_COST
    )
    if not power_ok and not workers_ok:
        return []
    actions: list[Action] = []
    for first, second in bridge_pairs(state.board):
        if frozenset((first, second)) in taken:
            continue
        if not (
            _has_building(state, player, first) or _has_building(state, player, second)
        ):
            continue
        if power_ok:
            actions.append(BuildBridge(first, second, "power"))
        if workers_ok:
            actions.append(BuildBridge(first, second, "workers"))
    return actions


def build_bridge(
    state: TerraMysticaState,
    player: PlayerId,
    first: Hex,
    second: Hex,
    payment: str = "power",
) -> Transition[TerraMysticaState]:
    """Pay for and place one bridge, then found any new towns."""
    if state.phase != "action":
        raise IllegalActionError("bridges can only be built during the action phase")
    if player != state.active_player:
        raise IllegalActionError(f"it is {seat_label(state.active_player)}'s turn")
    if _bridge_count(state, player) >= BRIDGE_SUPPLY:
        raise IllegalActionError("all three bridges are already placed")
    pair = (first, second) if first < second else (second, first)
    if pair not in bridge_pairs(state.board):
        raise IllegalActionError("those spaces are not joined by a river")
    if any((bridge.first, bridge.second) == pair for bridge in state.bridges):
        raise IllegalActionError("there is already a bridge there")
    if not (
        _has_building(state, player, first) or _has_building(state, player, second)
    ):
        raise IllegalActionError("a bridge needs a building on one of its ends")
    owner = state.players[player]
    burned = 0
    if payment == "power":
        if "bridge" in state.used_power_actions:
            raise IllegalActionError(
                "the power bridge action was already used this round"
            )
        cost = POWER_ACTION_COSTS["bridge"]
        if not can_spend_power(owner.resources, cost):
            raise IllegalActionError("you do not have enough power for a bridge")
        burned = power_shortfall(owner.resources.power3, cost)
        resources = burn_power(owner.resources, cost)
        assert resources is not None
        spent = spend_power(resources, cost)
        assert spent is not None
        owner = replace(owner, resources=spent)
        state = replace(state, used_power_actions=state.used_power_actions | {"bridge"})
    elif payment == "workers":
        if owner.profile.type is not FactionType.ENGINEERS:
            raise IllegalActionError("only the Engineers may pay workers for a bridge")
        if owner.resources.workers < ENGINEER_BRIDGE_COST:
            raise IllegalActionError("you need two workers for a bridge")
        owner = replace(
            owner,
            resources=replace(
                owner.resources,
                workers=owner.resources.workers - ENGINEER_BRIDGE_COST,
            ),
        )
    else:
        raise IllegalActionError("unknown bridge payment")
    state = replace_player(state, player, owner)
    bridge = Bridge(player, pair[0], pair[1])
    state = replace(state, bridges=(*state.bridges, bridge))
    board, resources, victory_points, keys, founded, town_events = town_rewards(
        state,
        player,
        state.board,
        pair[0],
        owner.resources,
        owner.victory_points,
        owner.keys,
    )
    owner = replace(
        owner,
        resources=resources,
        victory_points=victory_points,
        keys=keys,
    )
    state = replace_player(state, player, owner)
    state = replace(state, board=board)
    if founded:
        state = replace(state, towns=state.towns + founded)
    if payment == "power":
        text = (
            f"{seat_label(player)} built a bridge between {pair[0].notation()} "
            f"and {pair[1].notation()}"
        )
        if burned:
            text += (
                f", burning {2 * burned} Bowl II tokens and permanently losing "
                f"{burned} tokens"
            )
        text += "."
    else:
        text = (
            f"{seat_label(player)} built a bridge between {pair[0].notation()} "
            f"and {pair[1].notation()} for 2 workers."
        )
    events = [
        Event(
            "bridge_built",
            text,
            {
                "player": player,
                "first": pair[0].notation(),
                "second": pair[1].notation(),
                "payment": payment,
                "burned": burned,
            },
        ),
        *town_events,
    ]
    if founded and town_tile_actions(state):
        state = replace(
            state,
            phase="town_choice",
            active_player=player,
            pending_towns=founded,
        )
        return Transition(state, tuple(events))
    state = replace(state, phase="action", active_player=player)
    return advance_turn(state, player, tuple(events))


def explain_bridge(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    """Why a bridge action cannot be taken."""
    if not isinstance(action, BuildBridge):
        return "Choose a bridge to build."
    if state.phase != "action":
        return "Bridges can only be built during the action phase."
    if player != state.active_player:
        return f"It is {seat_label(state.active_player)}'s turn."
    if _bridge_count(state, player) >= BRIDGE_SUPPLY:
        return "All three bridges are already placed."
    pair = (
        (action.first, action.second)
        if action.first < action.second
        else (action.second, action.first)
    )
    if pair not in bridge_pairs(state.board):
        return "Those spaces are not joined by a river."
    if any((bridge.first, bridge.second) == pair for bridge in state.bridges):
        return "There is already a bridge there."
    if not (
        _has_building(state, player, action.first)
        or _has_building(state, player, action.second)
    ):
        return "A bridge needs a building on one of its ends."
    owner = state.players[player]
    if action.payment == "power":
        if "bridge" in state.used_power_actions:
            return "The power bridge action was already used this round."
        if not can_spend_power(owner.resources, POWER_ACTION_COSTS["bridge"]):
            return "You do not have enough power for a bridge."
    elif action.payment == "workers":
        if owner.profile.type is not FactionType.ENGINEERS:
            return "Only the Engineers may pay workers for a bridge."
        if owner.resources.workers < ENGINEER_BRIDGE_COST:
            return "You need two workers for a bridge."
    else:
        return "Unknown bridge payment."
    return "That bridge cannot be built now."
