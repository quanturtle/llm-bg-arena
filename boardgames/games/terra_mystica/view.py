"""Observation data, text rendering and action descriptions for Terra Mystica."""

from boardgames.core import (
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    seat_label,
    seats,
)
from boardgames.games.terra_mystica.constants import CULT_ORDER
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BuildDwelling,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TerraMysticaState,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
    cult_bonus_json,
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
        "'.' is empty. Actions: build q,r; transform q,r; "
        "upgrade q,r trading_house|temple|stronghold|sanctuary; shipping; "
        "digging; priest fire|water|earth|air 0-3; advance fire|water|earth|air; "
        "power priest|workers|coins; spade q,r; skip spade; pass."
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
    return f"{seat_label(PlayerId(active))} has {budget} cult-bonus spade(s)."


def player_lines(data: JsonObject) -> list[str]:
    lines: list[str] = []
    for player in _objects(data, "players"):
        seat = PlayerId(_int(player, "seat"))
        power = _ints(player, "power")
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
            f"power {'/'.join(str(value) for value in power)}, "
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
        case BuildDwelling(position=position):
            if observation.data.get("phase") == "setup":
                return f"Place a starting dwelling at {position.notation()}."
            return f"Build a dwelling at {position.notation()}."
        case TransformTerrain(position=position):
            return f"Transform {position.notation()} into your home terrain."
        case UpgradeBuilding(position=position, to=building):
            return f"Upgrade the building at {position.notation()} to {building.value}."
        case AdvanceShipping():
            return "Advance one step on the shipping track."
        case AdvanceDigging():
            return "Advance one step on the digging track."
        case SendPriest(cult=cult, order=order):
            return f"Send a priest to the {cult.value} order space {order}."
        case AdvanceCult(cult=cult):
            return f"Spend a priest to advance {cult.value} by one space."
        case PowerAction(kind=kind):
            return f"Spend power for {kind}."
        case UseCultSpade(position=position):
            return f"Use cult-bonus spades to transform {position.notation()}."
        case SkipCultSpade():
            return "Skip the remaining cult-bonus spades."
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


__all__ = ["describe_action", "observe", "render_text"]
