"""Observation data, text rendering and action descriptions for Terra Mystica."""

from boardgames.core import (
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    seat_label,
    seats,
)
from boardgames.games.terra_mystica.constants import (
    CULT_ORDER,
    FACTION_BY_TYPE,
    POWER_ACTION_COSTS,
    POWER_ACTION_TEXT,
    BuildingType,
    Cost,
    FactionProfile,
    FactionType,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BuildDwelling,
    ChooseStrongholdPriests,
    Hex,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TakeTownTile,
    TerraMysticaState,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
    building_cost,
    cult_bonus_json,
    power_shortfall,
    spade_cost,
    spades_for,
    terrain_distance,
)
from boardgames.games.terra_mystica.scoring import final_scores

TERRAIN_LETTERS = {
    "plains": "P",
    "swamp": "S",
    "lake": "L",
    "forest": "F",
    "mountain": "M",
    "wasteland": "W",
    "desert": "D",
    "river": "R",
}


def observe(state: TerraMysticaState, viewer: PlayerId | None) -> Observation:
    """Everything is public in Terra Mystica, so every viewer sees the same state."""
    players = seats(len(state.players))
    scoring = [tile.action.value for tile in state.scoring]
    data: dict[str, JsonValue] = {
        "round": state.round,
        "phase": state.phase,
        "active": state.active_player,
        "order": list(state.order),
        "scoring": scoring,
        "scoring_bonuses": [cult_bonus_json(tile.bonus) for tile in state.scoring],
        "cult_spades": list(state.cult_spades),
        "spade_return": state.spade_return,
        "town_tiles": list(state.town_tiles),
        "used_orders": [
            {"cult": cult.value, "order": order, "player": player}
            for (cult, order), player in sorted(
                state.used_orders.items(),
                key=lambda item: (CULT_ORDER.index(item[0][0]), item[0][1]),
            )
        ],
        "passed": sorted(state.passed),
        "pass_order": list(state.pass_order),
        "used_power_actions": sorted(state.used_power_actions),
        "setup_queue": list(state.setup_queue),
        "players": [player_data(state, seat) for seat in players],
        "board": [
            {
                "q": tile.position.q,
                "r": tile.position.r,
                "terrain": tile.terrain.value,
                "building": (
                    None
                    if tile.building is None
                    else {
                        "owner": tile.building.owner,
                        "type": tile.building.type.value,
                        "in_town": tile.building.in_town,
                    }
                ),
            }
            for tile in state.board.tiles
        ],
        "game_over": state.phase == "game_over",
        "end_reason": state.end_reason,
        "you": None if viewer is None else viewer,
    }
    if state.phase == "game_over":
        final = final_scores(state)
        data["final_scores"] = [
            {
                "player": seat,
                "points": final[seat][0],
                "breakdown": final[seat][1],
            }
            for seat in players
        ]
    else:
        data["final_scores"] = None
    return Observation(viewer, data)


def player_data(state: TerraMysticaState, seat: PlayerId) -> JsonObject:
    player = state.players[seat]
    return {
        "seat": seat,
        "faction": player.faction.value,
        "name": player.profile.name,
        "home_terrain": player.home_terrain.value,
        "victory_points": player.victory_points,
        "coins": player.resources.coins,
        "workers": player.resources.workers,
        "priests": player.resources.priests,
        "power": [
            player.resources.power1,
            player.resources.power2,
            player.resources.power3,
        ],
        "cults": {cult.value: player.cult(cult) for cult in CULT_ORDER},
        "shipping": player.shipping,
        "digging": player.digging,
        "keys": player.keys,
        "buildings": [
            {
                "position": position.notation(),
                "type": building.type.value,
                "in_town": building.in_town,
            }
            for position, building in state.board.buildings(seat)
        ],
    }


def render_text(observation: Observation) -> str:
    data = observation.data
    lines = [status_line(data)]
    lines.append(scoring_line(data))
    lines.append(cult_bonuses_line(data))
    lines.append(orders_line(data))
    lines.append(passed_line(data))
    lines.append(power_actions_line(data))
    spades = cult_spades_line(data)
    if spades:
        lines.append(spades)
    lines.extend(player_lines(data))
    lines.extend(board_lines(data))
    if observation.viewer is not None:
        lines.append(f"You are {seat_label(observation.viewer)}.")
    lines.extend(final_lines(data))
    lines.append("")
    lines.append(
        "Legend: P plains, S swamp, L lake, F forest, M mountain, "
        "W wasteland, D desert, R river. A digit is the owner of a building; "
        "'.' is empty. Actions: build q,r [river q,r]; transform q,r [to T]; "
        "upgrade q,r trading_house|temple|stronghold|sanctuary [river q,r]; "
        "shipping; digging; priest fire|water|earth|air 0-3; "
        "advance fire|water|earth|air; "
        "power priest|workers|coins|spade|double_spade; town 0-4; "
        "stronghold 0-3; spade q,r [to T]; skip spade; "
        "alchemist vp|coins; pass."
    )
    return "\n".join(lines)


def status_line(data: JsonObject) -> str:
    if data.get("game_over") is True:
        reason = data.get("end_reason")
        suffix = f" ({reason})" if isinstance(reason, str) else ""
        return f"Game over{suffix}."
    round_number = _int(data, "round")
    phase = _str(data, "phase")
    active = PlayerId(_int(data, "active"))
    scoring = _strings(data, "scoring")
    current = scoring[round_number - 1] if round_number <= len(scoring) else "?"
    return (
        f"Round {round_number}, {phase}: {seat_label(active)} to act. "
        f"This round scores {current}."
    )


def scoring_line(data: JsonObject) -> str:
    scoring = _strings(data, "scoring")
    return "Round scoring: " + ", ".join(scoring) + "."


def cult_bonuses_line(data: JsonObject) -> str:
    bonuses = _objects(data, "scoring_bonuses")
    if not bonuses:
        return "Cult bonuses: none."
    parts = [
        f"{_int(bonus, 'amount')} {_str(bonus, 'reward')} per "
        f"{_int(bonus, 'per')} {_str(bonus, 'cult')}"
        for bonus in bonuses
    ]
    return "Cult bonuses: " + ", ".join(parts) + "."


def orders_line(data: JsonObject) -> str:
    orders = _objects(data, "used_orders")
    if not orders:
        return "Claimed cult order spaces: none."
    parts = [
        f"{_str(order, 'cult')} {_int(order, 'order')} "
        f"({seat_label(PlayerId(_int(order, 'player')))})"
        for order in orders
    ]
    return "Claimed cult order spaces: " + ", ".join(parts) + "."


def passed_line(data: JsonObject) -> str:
    order = _ints(data, "pass_order")
    if not order:
        return "Passed: none."
    return (
        "Passed in order: "
        + ", ".join(seat_label(PlayerId(seat)) for seat in order)
        + "."
    )


def power_actions_line(data: JsonObject) -> str:
    actions = _strings(data, "used_power_actions")
    return "Power actions used this round: " + (", ".join(actions) or "none") + "."


def cult_spades_line(data: JsonObject) -> str:
    if _str(data, "phase") != "cult_spades":
        return ""
    active = _int(data, "active")
    budget = _ints(data, "cult_spades")[active]
    kind = "spade" if _str(data, "spade_return") == "action" else "cult-bonus spade"
    return f"{seat_label(PlayerId(active))} has {budget} {kind}(s)."


def player_lines(data: JsonObject) -> list[str]:
    lines: list[str] = []
    for player in _objects(data, "players"):
        seat = PlayerId(_int(player, "seat"))
        power = _ints(player, "power")
        bowls = (
            f"I:{power[0]} II:{power[1]} III:{power[2]}"
            if len(power) >= 3
            else "/".join(str(value) for value in power)
        )
        cults = _object(player, "cults")
        cult_text = " ".join(
            f"{cult.value[0].upper()}{_int(cults, cult.value)}" for cult in CULT_ORDER
        )
        buildings = [
            f"{_str(building, 'type')}@{_str(building, 'position')}"
            for building in _objects(player, "buildings")
        ]
        lines.append(
            f"{seat_label(seat)} {_str(player, 'name')}: "
            f"{_int(player, 'victory_points')} VP, "
            f"{_int(player, 'coins')}c {_int(player, 'workers')}w "
            f"{_int(player, 'priests')}p, "
            f"power bowls {bowls}, "
            f"cults {cult_text}, shipping {_int(player, 'shipping')}, "
            f"digging {_int(player, 'digging')}, keys {_int(player, 'keys')}, "
            f"home {_str(player, 'home_terrain')}. "
            f"Buildings: {', '.join(buildings) or 'none'}."
        )
    return lines


def board_lines(data: JsonObject) -> list[str]:
    tiles = _objects(data, "board")
    by_row: dict[int, list[JsonObject]] = {}
    for tile in tiles:
        by_row.setdefault(_int(tile, "r"), []).append(tile)
    lines = ["Board:"]
    for row in sorted(by_row):
        ordered = sorted(by_row[row], key=lambda item: _int(item, "q"))
        cells: list[str] = []
        for tile in ordered:
            terrain = _str(tile, "terrain")
            letter = TERRAIN_LETTERS.get(terrain, "?")
            building = tile.get("building")
            owner = "."
            if isinstance(building, dict):
                owner = str(_int(building, "owner") + 1)
            cells.append(f"{letter}{owner}")
        first_q = _int(ordered[0], "q")
        last_q = _int(ordered[-1], "q")
        lines.append(f"r{row} (q{first_q}..{last_q}): " + " ".join(cells))
    return lines


def final_lines(data: JsonObject) -> list[str]:
    final = data.get("final_scores")
    if not isinstance(final, list):
        return []
    lines = ["Final scores:"]
    for entry in final:
        if not isinstance(entry, dict):
            continue
        seat = PlayerId(_int(entry, "player"))
        breakdown = _object(entry, "breakdown")
        lines.append(
            f"  {seat_label(seat)}: {_int(entry, 'points')} points "
            f"(base {_int(breakdown, 'base')}, cult {_int(breakdown, 'cult')}, "
            f"area {_int(breakdown, 'area')}, resources "
            f"{_int(breakdown, 'resources')})."
        )
    return lines


def describe_action(observation: Observation, action: Action) -> str:
    match action:
        case BuildDwelling(position=position, river=river):
            if observation.data.get("phase") == "setup":
                return f"Place a starting dwelling at {position.notation()}."
            suffix = "" if river is None else f" across river {river.notation()}"
            detail = _build_detail(observation.data, position)
            return f"Build a dwelling at {position.notation()}{suffix}{detail}."
        case TransformTerrain(position=position, to=terrain):
            target = "your home terrain" if terrain is None else terrain.value
            detail = _transform_detail(observation.data, position, terrain)
            return f"Transform {position.notation()} into {target}{detail}."
        case UpgradeBuilding(position=position, to=building, river=river):
            suffix = "" if river is None else f" across river {river.notation()}"
            detail = _upgrade_detail(observation.data, position, building)
            return (
                f"Upgrade the building at {position.notation()} to "
                f"{building.value}{suffix}{detail}."
            )
        case AdvanceShipping():
            return "Advance one step on the shipping track."
        case AdvanceDigging():
            return "Advance one step on the digging track."
        case SendPriest(cult=cult, order=order):
            return f"Send a priest to the {cult.value} order space {order}."
        case AdvanceCult(cult=cult):
            return f"Spend a priest to advance {cult.value} by one space."
        case ChooseStrongholdPriests(workers=workers):
            return (
                f"Trade {workers} worker(s) for {workers} priest(s) as the "
                "Darklings' stronghold reward."
            )
        case TakeTownTile(index=index):
            return f"Take town tile {index}."
        case PowerAction(kind=kind):
            cost = POWER_ACTION_COSTS[kind]
            power = _ints(_active_player(observation.data), "power")
            charged = power[2] if len(power) > 2 else 0
            burned = power_shortfall(charged, cost)
            text = f"Spend {cost} power for {POWER_ACTION_TEXT[kind]}"
            if burned:
                text += (
                    f" (burn {_count(2 * burned, 'Bowl II token')} and permanently "
                    f"lose {_count(burned, 'token')})"
                )
            return text + "."
        case UseCultSpade(position=position, to=terrain):
            target = (
                "toward your home terrain" if terrain is None else f"to {terrain.value}"
            )
            spade_kind = (
                "spade"
                if observation.data.get("spade_return") == "action"
                else "cult-bonus spade"
            )
            detail = _spade_detail(observation.data, position, terrain)
            return f"Use {spade_kind}s at {position.notation()} {target}{detail}."
        case SkipCultSpade():
            spade_kind = (
                "spade"
                if observation.data.get("spade_return") == "action"
                else "cult-bonus spade"
            )
            return f"Skip the remaining {spade_kind}s."
        case TradeVpForCoin():
            return "Trade 1 victory point for 1 coin."
        case TradeCoinsForVp():
            return "Trade 2 coins for 1 victory point."
        case Pass():
            return "Pass."
    return "Take an action."


def _object(data: JsonObject, key: str) -> JsonObject:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _objects(data: JsonObject, key: str) -> list[JsonObject]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int(data: JsonObject, key: str) -> int:
    value = data.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _str(data: JsonObject, key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def _strings(data: JsonObject, key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _ints(data: JsonObject, key: str) -> list[int]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [
        item for item in value if isinstance(item, int) and not isinstance(item, bool)
    ]


def _active_player(data: JsonObject) -> JsonObject:
    active = _int(data, "active")
    return next(
        (
            player
            for player in _objects(data, "players")
            if _int(player, "seat") == active
        ),
        {},
    )


def _count(value: int, singular: str, plural: str | None = None) -> str:
    noun = singular if value == 1 else (plural or f"{singular}s")
    return f"{value} {noun}"


def _cost_text(cost: Cost) -> str:
    parts: list[str] = []
    if cost.coins:
        parts.append(_count(cost.coins, "coin"))
    if cost.workers:
        parts.append(_count(cost.workers, "worker"))
    if cost.priests:
        parts.append(_count(cost.priests, "priest"))
    if cost.power:
        parts.append(f"{cost.power} power")
    return " + ".join(parts) if parts else "free"


def _terrain(value: str) -> Terrain | None:
    try:
        return Terrain(value)
    except ValueError:
        return None


def _profile(player: JsonObject) -> FactionProfile | None:
    try:
        return FACTION_BY_TYPE[FactionType(_str(player, "faction"))]
    except ValueError:
        return None


def _tile_at(data: JsonObject, position: Hex) -> JsonObject:
    for tile in _objects(data, "board"):
        if _int(tile, "q") == position.q and _int(tile, "r") == position.r:
            return tile
    return {}


def _building_at(tile: JsonObject) -> JsonObject | None:
    building = tile.get("building")
    return building if isinstance(building, dict) else None


def _adjacent_owner(
    data: JsonObject, position: Hex, seat: int, *, opponent: bool
) -> bool:
    for neighbour in position.neighbours():
        building = _building_at(_tile_at(data, neighbour))
        if building is None:
            continue
        if (opponent and _int(building, "owner") != seat) or (
            not opponent and _int(building, "owner") == seat
        ):
            return True
    return False


def _reach_cost(player: JsonObject, profile: FactionProfile) -> Cost:
    has_stronghold = any(
        _str(building, "type") == BuildingType.STRONGHOLD.value
        for building in _objects(player, "buildings")
    )
    if has_stronghold and profile.reach_cost_with_stronghold is not None:
        return profile.reach_cost_with_stronghold
    return profile.reach_cost


def _spade_text(profile: FactionProfile, digging: int, spades: int) -> str:
    return (
        f"{_count(spades, 'spade')} = "
        f"{_cost_text(spade_cost(profile, digging, spades))}"
    )


def _terrain_cost_text(
    player: JsonObject, profile: FactionProfile, source: Terrain, target: Terrain
) -> str:
    spades = (
        spades_for(profile, source)
        if target is profile.home_terrain
        else terrain_distance(source, target)
    )
    if spades <= 0:
        return ""
    return (
        f"{source.value} -> {target.value}: "
        f"{_spade_text(profile, _int(player, 'digging'), spades)}"
    )


def _build_detail(data: JsonObject, position: Hex) -> str:
    player = _active_player(data)
    profile = _profile(player)
    tile = _tile_at(data, position)
    source = _terrain(_str(tile, "terrain"))
    if profile is None or source is None:
        return ""
    parts: list[str] = []
    if source is profile.home_terrain:
        parts.append(f"{source.value} (home)")
    else:
        parts.append(_terrain_cost_text(player, profile, source, profile.home_terrain))
    build_cost = building_cost(
        profile,
        BuildingType.DWELLING,
        _adjacent_owner(data, position, _int(player, "seat"), opponent=True),
    )
    parts.append(f"building {_cost_text(build_cost)}")
    if (
        data.get("phase") != "cult_spades"
        and profile.reach > 0
        and not _adjacent_owner(data, position, _int(player, "seat"), opponent=False)
    ):
        route = "tunnel" if profile.reach_cost.workers else "carpet flight"
        parts.append(f"{route} {_cost_text(_reach_cost(player, profile))}")
    return " (" + "; ".join(part for part in parts if part) + ")"


def _transform_detail(data: JsonObject, position: Hex, target: Terrain | None) -> str:
    player = _active_player(data)
    profile = _profile(player)
    tile = _tile_at(data, position)
    source = _terrain(_str(tile, "terrain"))
    if profile is None or source is None:
        return ""
    destination = target or profile.home_terrain
    parts = [_terrain_cost_text(player, profile, source, destination)]
    if profile.reach > 0 and not _adjacent_owner(
        data, position, _int(player, "seat"), opponent=False
    ):
        parts.append(f"tunnel {_cost_text(_reach_cost(player, profile))}")
    return " (" + "; ".join(part for part in parts if part) + ")"


def _upgrade_detail(data: JsonObject, position: Hex, target: BuildingType) -> str:
    player = _active_player(data)
    profile = _profile(player)
    if profile is None:
        return ""
    cost = building_cost(
        profile,
        target,
        _adjacent_owner(data, position, _int(player, "seat"), opponent=True),
    )
    return f" (cost {_cost_text(cost)})"


def _spade_detail(data: JsonObject, position: Hex, target: Terrain | None) -> str:
    player = _active_player(data)
    profile = _profile(player)
    tile = _tile_at(data, position)
    source = _terrain(_str(tile, "terrain"))
    if profile is None or source is None:
        return ""
    destination = target or profile.home_terrain
    full = (
        spades_for(profile, source)
        if destination is profile.home_terrain
        else terrain_distance(source, destination)
    )
    if full <= 0:
        return ""
    budget = _ints(data, "cult_spades")
    active = _int(data, "active")
    available = budget[active] if active < len(budget) else 0
    missing = max(0, full - available)
    if missing == 0:
        parts = [f"{_count(full, 'spade')}, already paid"]
    else:
        cost = spade_cost(profile, _int(player, "digging"), missing)
        parts = [
            f"{_count(full, 'spade')}; {_count(missing, 'spade')} missing = "
            f"{_cost_text(cost)}"
        ]
    if (
        data.get("spade_return") == "action"
        and profile.reach > 0
        and not _adjacent_owner(data, position, _int(player, "seat"), opponent=False)
    ):
        route = "tunnel" if profile.reach_cost.workers else "carpet flight"
        parts.append(f"{route} {_cost_text(_reach_cost(player, profile))}")
    return " (" + "; ".join(parts) + ")"


__all__ = ["describe_action", "observe", "render_text"]
