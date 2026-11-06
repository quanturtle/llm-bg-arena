"""Terra Mystica building: dwellings, terraforming, upgrades and the two tracks."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.terra_mystica.constants import (
    MAX_BUILDINGS,
    SCORING_VALUES,
    TERRAIN_WHEEL,
    TOWN_SUPPLY,
    BuildingType,
    Cost,
    FactionProfile,
    FactionType,
    ScoringAction,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceDigging,
    AdvanceShipping,
    Board,
    BuildDwelling,
    Building,
    Hex,
    TerraMysticaState,
    TransformTerrain,
    UpgradeBuilding,
    add_costs,
    building_cost,
    can_pay,
    can_place_building,
    effective_reach,
    effective_reach_cost,
    pay,
    replace_player,
    shipping_cost,
    shipping_points,
    spade_cost,
    spades_for,
    terrain_distance,
)
from boardgames.games.terra_mystica.rounds import advance_turn, round_scoring
from boardgames.games.terra_mystica.strongholds import stronghold_reward
from boardgames.games.terra_mystica.towns import (
    build_river_choices,
    town_rewards,
    upgrade_river_choices,
)


def adjacent_to_own(board: Board, player: PlayerId, position: Hex) -> bool:
    """Whether one of the player's structures shares an edge with `position`."""
    return any(
        (tile := board.tile(neighbour)) is not None
        and tile.building is not None
        and tile.building.owner == player
        for neighbour in position.neighbours()
    )


def build_dwelling(
    state: TerraMysticaState,
    player: PlayerId,
    position: Hex,
    river: Hex | None = None,
    *,
    reach_paid: bool = False,
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(position)
    if tile is None:
        raise IllegalActionError("there is no tile there")
    if not tile.is_land:
        raise IllegalActionError("you cannot build on a river")
    if tile.building is not None:
        raise IllegalActionError("that tile is occupied")
    if (
        state.board.count(player, BuildingType.DWELLING)
        >= MAX_BUILDINGS[BuildingType.DWELLING]
    ):
        raise IllegalActionError("you have no dwellings left")
    reach = effective_reach(state.board, player, profile)
    if position not in state.board.reachable_land(player, owner.shipping, reach):
        raise IllegalActionError(
            "the tile must be directly or indirectly adjacent to one of your structures"
        )
    tunneling = reach > 0 and not adjacent_to_own(state.board, player, position)
    spades = spades_for(profile, tile.terrain)
    terrain_cost = spade_cost(profile, owner.digging, spades)
    build_cost = building_cost(
        profile,
        BuildingType.DWELLING,
        bool(state.board.adjacent_opponents(position, player)),
    )
    reach_cost = (
        effective_reach_cost(state.board, player, profile)
        if tunneling and not reach_paid
        else Cost()
    )
    total = add_costs(add_costs(terrain_cost, build_cost), reach_cost)
    if not can_pay(owner.resources, total):
        raise IllegalActionError("you cannot pay for that transform, build and tunnel")
    resources = pay(owner.resources, total)
    board = state.board
    if spades:
        board = board.replace_tile(
            position, replace(tile, terrain=profile.home_terrain)
        )
    board = board.place(position, Building(BuildingType.DWELLING, player))
    victory_points = owner.victory_points
    if spades:
        victory_points += spades * profile.spade_vp_bonus
        if round_scoring(state) is ScoringAction.SPADE:
            victory_points += spades * SCORING_VALUES[ScoringAction.SPADE]
    if tunneling and not reach_paid:
        victory_points += profile.reach_vp
    if round_scoring(state) is ScoringAction.DWELLING:
        victory_points += SCORING_VALUES[ScoringAction.DWELLING]
    board, resources, victory_points, keys, founded = town_rewards(
        state,
        player,
        board,
        position,
        resources,
        victory_points,
        owner.keys,
        river=river,
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
        state = replace(state, towns=state.towns + 1)
    route = ""
    if tunneling:
        route = " by tunneling" if profile.reach_cost.workers else " by carpet flight"
    events = [
        Event(
            "built",
            f"{seat_label(player)} built a dwelling at {position.notation()}"
            + route
            + (f" after using {spades} spade(s)." if spades else "."),
            {
                "player": player,
                "position": position.notation(),
                "building": "dwelling",
                "spades": spades,
                "tunnel": tunneling,
            },
        )
    ]
    if founded:
        events.append(
            Event(
                "town_founded",
                f"{seat_label(player)} founded a town at {position.notation()}.",
                {"player": player, "position": position.notation()},
            )
        )
        state = replace(state, phase="town_choice", active_player=player)
        return Transition(state, tuple(events))
    return advance_turn(state, player, tuple(events))


def transform_terrain(
    state: TerraMysticaState,
    player: PlayerId,
    position: Hex,
    to: Terrain | None = None,
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(position)
    if tile is None:
        raise IllegalActionError("there is no tile there")
    if not tile.is_land:
        raise IllegalActionError("you cannot transform a river")
    if tile.building is not None:
        raise IllegalActionError("that tile is occupied")
    reach = effective_reach(state.board, player, profile)
    if position not in state.board.reachable_land(player, owner.shipping, reach):
        raise IllegalActionError(
            "the tile must be directly or indirectly adjacent to one of your structures"
        )
    target = to or profile.home_terrain
    if target is tile.terrain:
        raise IllegalActionError("that tile is already that terrain")
    if profile.terraform_spades is not None and target is not profile.home_terrain:
        raise IllegalActionError("the Giants can only transform to home terrain")
    tunneling = reach > 0 and not adjacent_to_own(state.board, player, position)
    spades = spades_for(profile, tile.terrain)
    if target is not profile.home_terrain:
        spades = terrain_distance(tile.terrain, target)
    cost = spade_cost(profile, owner.digging, spades)
    if tunneling:
        cost = add_costs(cost, effective_reach_cost(state.board, player, profile))
    if not can_pay(owner.resources, cost):
        raise IllegalActionError("you cannot pay for that transformation")
    resources = pay(owner.resources, cost)
    board = state.board.replace_tile(position, replace(tile, terrain=target))
    victory_points = owner.victory_points + spades * profile.spade_vp_bonus
    if tunneling:
        victory_points += profile.reach_vp
    if round_scoring(state) is ScoringAction.SPADE:
        victory_points += spades * SCORING_VALUES[ScoringAction.SPADE]
    owner = replace(owner, resources=resources, victory_points=victory_points)
    state = replace_player(state, player, owner)
    state = replace(state, board=board)
    route = ""
    if tunneling:
        route = " by tunneling" if profile.reach_cost.workers else " by carpet flight"
    event = Event(
        "transformed",
        f"{seat_label(player)} transformed {position.notation()} into "
        f"{target.value} with {spades} spade(s){route}.",
        {
            "player": player,
            "position": position.notation(),
            "terrain": target.value,
            "spades": spades,
            "tunnel": tunneling,
        },
    )
    return advance_turn(state, player, (event,))


def _valid_upgrade(source: BuildingType, target: BuildingType) -> bool:
    return (
        (source is BuildingType.DWELLING and target is BuildingType.TRADING_HOUSE)
        or (
            source is BuildingType.TRADING_HOUSE
            and target in (BuildingType.TEMPLE, BuildingType.STRONGHOLD)
        )
        or (source is BuildingType.TEMPLE and target is BuildingType.SANCTUARY)
    )


def _scored_upgrade(
    action: ScoringAction, target: BuildingType
) -> ScoringAction | None:
    """The round scoring action an upgrade satisfies, if any."""
    if target is BuildingType.TRADING_HOUSE and action is ScoringAction.TRADING_HOUSE:
        return action
    if target in (BuildingType.STRONGHOLD, BuildingType.SANCTUARY) and (
        action is ScoringAction.STRONGHOLD_OR_SANCTUARY
    ):
        return action
    return None


def upgrade_building(
    state: TerraMysticaState,
    player: PlayerId,
    position: Hex,
    target: BuildingType,
    river: Hex | None = None,
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(position)
    if tile is None or tile.building is None:
        raise IllegalActionError("there is no building there")
    if tile.building.owner != player:
        raise IllegalActionError("that building belongs to another player")
    if not _valid_upgrade(tile.building.type, target):
        raise IllegalActionError(
            f"{tile.building.type.value} cannot be upgraded to {target.value}"
        )
    if state.board.count(player, target) >= MAX_BUILDINGS[target]:
        raise IllegalActionError(f"you have no {target.value} left")
    cost = building_cost(
        profile,
        target,
        bool(state.board.adjacent_opponents(position, player)),
    )
    if not can_pay(owner.resources, cost):
        raise IllegalActionError("you cannot afford that upgrade")
    resources = pay(owner.resources, cost)
    building = replace(tile.building, type=target, in_town=tile.building.in_town)
    board = state.board.replace_tile(position, replace(tile, building=building))
    victory_points = owner.victory_points
    scored = _scored_upgrade(round_scoring(state), target)
    if scored is not None:
        victory_points += SCORING_VALUES[scored]
    board, resources, victory_points, keys, founded = town_rewards(
        state,
        player,
        board,
        position,
        resources,
        victory_points,
        owner.keys,
        river=river,
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
        state = replace(state, towns=state.towns + 1)
    events = [
        Event(
            "upgraded",
            f"{seat_label(player)} upgraded {position.notation()} to {target.value}.",
            {
                "player": player,
                "position": position.notation(),
                "building": target.value,
            },
        )
    ]
    if founded:
        events.append(
            Event(
                "town_founded",
                f"{seat_label(player)} founded a town at {position.notation()}.",
                {"player": player, "position": position.notation()},
            )
        )
    if target is BuildingType.STRONGHOLD:
        if founded:
            state = replace(
                state,
                phase="town_choice",
                active_player=player,
                pending_stronghold=True,
            )
            return Transition(state, tuple(events))
        state, events = stronghold_reward(state, player, events)
        if state.phase in ("cult_spades", "stronghold_convert"):
            return Transition(state, tuple(events))
    if founded:
        state = replace(state, phase="town_choice", active_player=player)
        return Transition(state, tuple(events))
    return advance_turn(state, player, tuple(events))


def advance_shipping(
    state: TerraMysticaState, player: PlayerId
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    cost = shipping_cost()
    owner = replace(
        owner,
        resources=pay(owner.resources, cost),
        shipping=owner.shipping + 1,
        victory_points=owner.victory_points
        + shipping_points(owner.shipping + 1, owner.profile.shipping_start),
    )
    state = replace_player(state, player, owner)
    event = Event(
        "shipping_advanced",
        f"{seat_label(player)} advanced to shipping {owner.shipping}.",
        {"player": player, "shipping": owner.shipping},
    )
    return advance_turn(state, player, (event,))


def advance_digging(
    state: TerraMysticaState, player: PlayerId
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    cost = owner.profile.digging_cost
    owner = replace(
        owner,
        resources=pay(owner.resources, cost),
        digging=owner.digging + 1,
        victory_points=owner.victory_points + 6,
    )
    state = replace_player(state, player, owner)
    event = Event(
        "digging_advanced",
        f"{seat_label(player)} advanced to digging {owner.digging}.",
        {"player": player, "digging": owner.digging},
    )
    return advance_turn(state, player, (event,))


def _dwelling_actions(
    state: TerraMysticaState, player: PlayerId, build_reachable: set[Hex]
) -> list[Action]:
    owner = state.players[player]
    profile = owner.profile
    resources = owner.resources
    reach_cost = effective_reach_cost(state.board, player, profile)
    actions: list[Action] = []
    if not can_place_building(state.board, player, BuildingType.DWELLING):
        return actions
    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        if tile.position not in build_reachable:
            continue
        spades = spades_for(profile, tile.terrain)
        terrain_cost = spade_cost(profile, owner.digging, spades)
        build_cost = building_cost(
            profile,
            BuildingType.DWELLING,
            bool(state.board.adjacent_opponents(tile.position, player)),
        )
        tunneling = profile.reach > 0 and not adjacent_to_own(
            state.board, player, tile.position
        )
        total = add_costs(terrain_cost, build_cost)
        if tunneling:
            total = add_costs(total, reach_cost)
        if can_pay(resources, total):
            actions.append(BuildDwelling(tile.position))
            for river in build_river_choices(
                state.board,
                player,
                profile,
                tile.position,
                TOWN_SUPPLY - state.towns,
            ):
                actions.append(BuildDwelling(tile.position, river=river))
    return actions


def _transform_actions(
    state: TerraMysticaState, player: PlayerId, build_reachable: set[Hex]
) -> list[Action]:
    owner = state.players[player]
    profile = owner.profile
    resources = owner.resources
    reach_cost = effective_reach_cost(state.board, player, profile)
    actions: list[Action] = []
    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        if tile.position not in build_reachable:
            continue
        if profile.terraform_spades is not None:
            if tile.terrain is profile.home_terrain:
                continue
            cost = spade_cost(profile, owner.digging, spades_for(profile, tile.terrain))
            if profile.reach > 0 and not adjacent_to_own(
                state.board, player, tile.position
            ):
                cost = add_costs(cost, reach_cost)
            if can_pay(resources, cost):
                actions.append(TransformTerrain(tile.position))
            continue
        for target in TERRAIN_WHEEL:
            if target is tile.terrain:
                continue
            cost = spade_cost(
                profile,
                owner.digging,
                terrain_distance(tile.terrain, target),
            )
            if profile.reach > 0 and not adjacent_to_own(
                state.board, player, tile.position
            ):
                cost = add_costs(cost, reach_cost)
            if not can_pay(resources, cost):
                continue
            if target is profile.home_terrain:
                actions.append(TransformTerrain(tile.position))
            else:
                actions.append(TransformTerrain(tile.position, target))
    return actions


def _append_upgrade(
    actions: list[Action],
    board: Board,
    player: PlayerId,
    profile: FactionProfile,
    position: Hex,
    target: BuildingType,
    towns_left: int,
) -> None:
    """List an upgrade and each Mermaid river skip that changes its town."""
    actions.append(UpgradeBuilding(position, target))
    for river in upgrade_river_choices(
        board, player, profile, position, target, towns_left
    ):
        actions.append(UpgradeBuilding(position, target, river=river))


def _upgrade_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    profile = owner.profile
    resources = owner.resources
    actions: list[Action] = []
    for position, building in state.board.buildings(player):
        if building.type is BuildingType.DWELLING and can_place_building(
            state.board, player, BuildingType.TRADING_HOUSE
        ):
            cost = building_cost(
                profile,
                BuildingType.TRADING_HOUSE,
                bool(state.board.adjacent_opponents(position, player)),
            )
            if can_pay(resources, cost):
                _append_upgrade(
                    actions,
                    state.board,
                    player,
                    profile,
                    position,
                    BuildingType.TRADING_HOUSE,
                    TOWN_SUPPLY - state.towns,
                )
        if (
            building.type is BuildingType.TRADING_HOUSE
            and can_place_building(state.board, player, BuildingType.TEMPLE)
            and can_pay(resources, profile.costs.temple)
        ):
            _append_upgrade(
                actions,
                state.board,
                player,
                profile,
                position,
                BuildingType.TEMPLE,
                TOWN_SUPPLY - state.towns,
            )
        if (
            building.type is BuildingType.TRADING_HOUSE
            and can_place_building(state.board, player, BuildingType.STRONGHOLD)
            and can_pay(resources, profile.costs.stronghold)
        ):
            _append_upgrade(
                actions,
                state.board,
                player,
                profile,
                position,
                BuildingType.STRONGHOLD,
                TOWN_SUPPLY - state.towns,
            )
        if (
            building.type is BuildingType.TEMPLE
            and can_place_building(state.board, player, BuildingType.SANCTUARY)
            and can_pay(resources, profile.costs.sanctuary)
        ):
            _append_upgrade(
                actions,
                state.board,
                player,
                profile,
                position,
                BuildingType.SANCTUARY,
                TOWN_SUPPLY - state.towns,
            )
    return actions


def _shipping_reason(state: TerraMysticaState, player: PlayerId) -> str | None:
    owner = state.players[player]
    if not owner.profile.can_ship:
        return "Your faction has no shipping track."
    if owner.shipping >= owner.profile.shipping_max:
        return "Your shipping track is already at its maximum."
    if not can_pay(owner.resources, shipping_cost()):
        return "Shipping costs 1 priest and 4 coins."
    return None


def _digging_reason(state: TerraMysticaState, player: PlayerId) -> str | None:
    owner = state.players[player]
    if not owner.profile.can_dig:
        return "Your faction cannot improve its digging."
    if owner.digging >= owner.profile.digging_max:
        return "Your digging track is already at its maximum."
    if not can_pay(owner.resources, owner.profile.digging_cost):
        return "You cannot pay for a digging step."
    return None


def _track_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    actions: list[Action] = []
    if _shipping_reason(state, player) is None:
        actions.append(AdvanceShipping())
    if _digging_reason(state, player) is None:
        actions.append(AdvanceDigging())
    return actions


def building_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    """Builds, transforms, upgrades, then shipping and digging, in listing order."""
    owner = state.players[player]
    build_reachable = set(
        state.board.reachable_land(
            player, owner.shipping, effective_reach(state.board, player, owner.profile)
        )
    )
    return [
        *_dwelling_actions(state, player, build_reachable),
        *_transform_actions(state, player, build_reachable),
        *_upgrade_actions(state, player),
        *_track_actions(state, player),
    ]


def explain_build(
    state: TerraMysticaState, player: PlayerId, action: BuildDwelling
) -> str:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(action.position)
    if tile is None:
        return "There is no tile there."
    if not tile.is_land:
        return "You cannot build on a river."
    if tile.building is not None:
        return "That tile is occupied."
    if action.river is not None:
        if profile.type is not FactionType.MERMAIDS:
            return "Only the Mermaids may join a town across the river."
        if action.river not in build_river_choices(
            state.board,
            player,
            profile,
            action.position,
            TOWN_SUPPLY - state.towns,
        ):
            return "That river does not change the town here."
    if (
        state.board.count(player, BuildingType.DWELLING)
        >= MAX_BUILDINGS[BuildingType.DWELLING]
    ):
        return "You have no dwellings left."
    reach = effective_reach(state.board, player, profile)
    if action.position not in state.board.reachable_land(player, owner.shipping, reach):
        return (
            "The tile must be directly or indirectly adjacent to one of "
            "your structures."
        )
    spades = spades_for(profile, tile.terrain)
    total = add_costs(
        spade_cost(profile, owner.digging, spades),
        building_cost(
            profile,
            BuildingType.DWELLING,
            bool(state.board.adjacent_opponents(action.position, player)),
        ),
    )
    if reach > 0 and not adjacent_to_own(state.board, player, action.position):
        total = add_costs(total, effective_reach_cost(state.board, player, profile))
    if not can_pay(owner.resources, total):
        return "You cannot pay for that transform, build and tunnel."
    return "That dwelling cannot be built now."


def explain_transform(
    state: TerraMysticaState, player: PlayerId, action: TransformTerrain
) -> str:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(action.position)
    if tile is None:
        return "There is no tile there."
    if not tile.is_land:
        return "You cannot transform a river."
    if tile.building is not None:
        return "That tile is occupied."
    target = action.to or profile.home_terrain
    if target is tile.terrain:
        return "That tile is already that terrain."
    if profile.terraform_spades is not None and target is not profile.home_terrain:
        return "The Giants can only transform to home terrain."
    reach = effective_reach(state.board, player, profile)
    if action.position not in state.board.reachable_land(player, owner.shipping, reach):
        return (
            "The tile must be directly or indirectly adjacent to one of "
            "your structures."
        )
    spades = spades_for(profile, tile.terrain)
    if target is not profile.home_terrain:
        spades = terrain_distance(tile.terrain, target)
    transform_cost = spade_cost(profile, owner.digging, spades)
    if reach > 0 and not adjacent_to_own(state.board, player, action.position):
        transform_cost = add_costs(
            transform_cost,
            effective_reach_cost(state.board, player, profile),
        )
    if not can_pay(owner.resources, transform_cost):
        return "You cannot pay for that transformation."
    return "That transformation is not legal now."


def explain_upgrade(
    state: TerraMysticaState, player: PlayerId, action: UpgradeBuilding
) -> str:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(action.position)
    if tile is None or tile.building is None:
        return "There is no building there."
    if tile.building.owner != player:
        return "That building belongs to another player."
    if not _valid_upgrade(tile.building.type, action.to):
        return f"{tile.building.type.value} cannot be upgraded to {action.to.value}."
    if state.board.count(player, action.to) >= MAX_BUILDINGS[action.to]:
        return f"You have no {action.to.value} left."
    if action.river is not None:
        if profile.type is not FactionType.MERMAIDS:
            return "Only the Mermaids may join a town across the river."
        if action.river not in upgrade_river_choices(
            state.board,
            player,
            profile,
            action.position,
            action.to,
            TOWN_SUPPLY - state.towns,
        ):
            return "That river does not change the town here."
    upgrade_cost = building_cost(
        profile,
        action.to,
        bool(state.board.adjacent_opponents(action.position, player)),
    )
    if not can_pay(owner.resources, upgrade_cost):
        return "You cannot afford that upgrade."
    return "That upgrade is not legal now."


def explain_shipping(state: TerraMysticaState, player: PlayerId) -> str:
    return _shipping_reason(state, player) or "You cannot advance shipping now."


def explain_digging(state: TerraMysticaState, player: PlayerId) -> str:
    return _digging_reason(state, player) or "You cannot advance digging now."
