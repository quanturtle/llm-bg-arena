"""Observation data, text rendering and action descriptions for Puerto Rico."""

from boardgames.core import (
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    seat_label,
    seats,
)
from boardgames.core.json_data import (
    json_bool,
    json_int,
    json_optional_int,
    json_str,
    json_str_list,
)
from boardgames.games.puerto_rico.constants import GOODS
from boardgames.games.puerto_rico.model import (
    Action,
    Build,
    DiscardGoods,
    FinishPlacement,
    LoadShip,
    LoadWharf,
    Pass,
    PickUpColonist,
    PlaceColonist,
    ProducePrivilege,
    PuertoRicoState,
    SelectRole,
    Sell,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
    building_points,
    city_spaces_used,
    end_game_bonus,
    goods_json_map,
    island_spaces_used,
    occupied_island_spaces,
    public_points,
    total_points,
)


def observe(state: PuertoRicoState, viewer: PlayerId | None) -> Observation:
    """What `viewer` may see: public board plus their own VP chips."""
    players = seats(state.config.num_players)
    is_over = state.phase == "game_over"
    data: dict[str, JsonValue] = {
        "round": state.round,
        "phase": state.phase,
        "governor": state.governor,
        "order": list(state.order),
        "active": state.active_player,
        "active_role": state.active_role,
        "roles": [
            {
                "role": role.role,
                "doubloons": role.doubloons,
                "taken_by": role.taken_by,
            }
            for role in state.roles
        ],
        "colonist_ship": state.colonist_ship,
        "colonist_supply": state.colonist_supply,
        "colonist_shortage": state.colonist_shortage,
        "vp_supply": state.vp_supply,
        "trading_house": list(state.trading_house),
        "cargo_ships": [
            {
                "capacity": ship.capacity,
                "good": ship.good,
                "filled": ship.filled,
            }
            for ship in state.cargo_ships
        ],
        "face_up": list(state.face_up),
        "plantation_deck_count": len(state.plantation_deck),
        "plantation_discard_count": len(state.plantation_discard),
        "available_buildings": list(state.available_buildings),
        "quarry_supply": state.quarry_supply,
        "goods_supply": goods_json_map(state.goods_supply),
        "players": [player_data(state, player, is_over) for player in players],
        "game_over": is_over,
        "winner": state.winner,
        "end_reason": state.end_reason,
        "final_scores": (
            [
                {
                    "player": player,
                    "points": total_points(state.players[player]),
                    "vp_chips": state.players[player].vp_chips,
                    "breakdown": point_breakdown(state, player),
                }
                for player in players
            ]
            if is_over
            else None
        ),
        "you": None if viewer is None else viewer_data(state, viewer),
    }
    return Observation(viewer, data)


def point_breakdown(state: PuertoRicoState, player: PlayerId) -> dict[str, JsonValue]:
    owner = state.players[player]
    return {
        "vp_chips": owner.vp_chips,
        "buildings": building_points(owner),
        "bonus": end_game_bonus(owner),
    }


def player_data(
    state: PuertoRicoState, player: PlayerId, reveal: bool
) -> dict[str, JsonValue]:
    owner = state.players[player]
    data: dict[str, JsonValue] = {
        "seat": player,
        "doubloons": owner.doubloons,
        "goods": goods_json_map(owner.goods),
        "plantations": [
            {"good": plantation.good, "colonized": plantation.colonized}
            for plantation in owner.plantations
        ],
        "quarries": owner.quarries,
        "occupied_quarries": owner.occupied_quarries,
        "buildings": [
            {
                "name": building.name,
                "colonists": building.colonists,
                "active": building.active,
            }
            for building in owner.buildings
        ],
        "colonists_unplaced": owner.colonists_unplaced,
        "city_spaces_used": city_spaces_used(owner),
        "island_spaces_used": island_spaces_used(owner),
        "occupied_island_spaces": occupied_island_spaces(owner),
        "building_points": building_points(owner),
        "public_points": public_points(owner),
    }
    if reveal:
        data["vp_chips"] = owner.vp_chips
        data["points"] = total_points(owner)
    return data


def viewer_data(state: PuertoRicoState, viewer: PlayerId) -> dict[str, JsonValue]:
    owner = state.players[viewer]
    return {
        "seat": viewer,
        "vp_chips": owner.vp_chips,
        "points": total_points(owner),
        "breakdown": point_breakdown(state, viewer),
    }


def render_text(observation: Observation) -> str:
    """Compact state for prompts and the CLI."""
    data = observation.data
    lines = [status_line(data)]
    lines.append(roles_line(data))
    lines.append(supplies_line(data))
    lines.append(face_up_line(data))
    lines.append(buildings_line(data))
    lines.extend(player_lines(data))
    if observation.viewer is not None:
        lines.append(f"You are {seat_label(observation.viewer)}.")
        you = data["you"]
        if isinstance(you, dict):
            lines.append(
                "Your victory point chips: "
                f"{json_int(you, 'vp_chips')}; total points: "
                f"{json_int(you, 'points')}."
            )
    lines.extend(final_lines(data))
    lines.append("")
    lines.append(
        "Legend: role = role card, doubloons = money. "
        "take <good> = take a face-up plantation, take quarry = take a quarry; "
        "`nohospice` declines the optional Hospice colonist. "
        "build <name> = build a building; `nouniversity` declines its optional "
        "colonist. sell <good> = sell to the trading house. "
        "ship <good> s<n> = load a cargo ship. wharf <good> = load the Wharf. "
        "place/pick plantation|building <i>, place/pick quarry. "
        "discard none = keep nothing unprotected; discard [protected...] none = "
        "keep only warehouses; add keep <good> to keep one good."
    )
    return "\n".join(lines)


def status_line(data: JsonObject) -> str:
    if json_bool(data, "game_over"):
        winner = json_optional_int(data, "winner")
        reason = data.get("end_reason")
        text = "Game over"
        if winner is not None:
            text = f"Game over: {seat_label(PlayerId(winner))} won"
        text = f"{text} ({reason})." if isinstance(reason, str) else f"{text}."
        return text
    active = PlayerId(json_int(data, "active"))
    phase = json_str(data, "phase")
    round_number = json_int(data, "round")
    role = data.get("active_role")
    role_text = f" ({role})" if isinstance(role, str) else ""
    return f"Round {round_number}, {phase}{role_text}: {seat_label(active)} acts."


def roles_line(data: JsonObject) -> str:
    parts: list[str] = []
    for role in _objects(data, "roles"):
        name = json_str(role, "role")
        doubloons = json_int(role, "doubloons")
        taken = json_optional_int(role, "taken_by")
        marker = "" if taken is None else f" taken by {seat_label(PlayerId(taken))}"
        parts.append(f"{name} ({doubloons}d{marker})")
    return "Roles: " + ", ".join(parts) + "."


def supplies_line(data: JsonObject) -> str:
    goods = _object(data, "goods_supply")
    goods_text = ", ".join(
        f"{good} {json_int(goods, good)}" for good in GOODS if good in goods
    )
    trading = json_str_list(data, "trading_house")
    ships: list[str] = []
    for ship in _objects(data, "cargo_ships"):
        good = ship.get("good")
        filled = json_int(ship, "filled")
        capacity = json_int(ship, "capacity")
        ships.append(f"{good or 'empty'} {filled}/{capacity}")
    shortage = (
        " The colonist supply cannot refill the ship; the game ends this round."
        if json_bool(data, "colonist_shortage")
        else ""
    )
    return (
        f"Supply: colonists ship {json_int(data, 'colonist_ship')}, "
        f"colonists {json_int(data, 'colonist_supply')}, "
        f"VP {json_int(data, 'vp_supply')}, quarries "
        f"{json_int(data, 'quarry_supply')}. Goods: {goods_text}. "
        f"Trading house: {', '.join(trading) or 'empty'}. "
        f"Ships: {', '.join(ships)}.{shortage}"
    )


def face_up_line(data: JsonObject) -> str:
    face_up = json_str_list(data, "face_up")
    return "Face-up plantations: " + (", ".join(face_up) or "none") + "."


def buildings_line(data: JsonObject) -> str:
    available = json_str_list(data, "available_buildings")
    counts: dict[str, int] = {}
    for name in available:
        counts[name] = counts.get(name, 0) + 1
    parts = [f"{name} x{count}" for name, count in counts.items()]
    return "Buildings available: " + (", ".join(parts) or "none") + "."


def player_lines(data: JsonObject) -> list[str]:
    lines: list[str] = []
    for player in _objects(data, "players"):
        seat = PlayerId(json_int(player, "seat"))
        goods = _object(player, "goods")
        goods_text = ", ".join(
            f"{good} {json_int(goods, good)}" for good in GOODS if good in goods
        )
        plantations = [
            f"{json_str(item, 'good')}{'*' if json_bool(item, 'colonized') else ''}"
            for item in _objects(player, "plantations")
        ]
        buildings = [
            f"{json_str(item, 'name')}({json_int(item, 'colonists')})"
            for item in _objects(player, "buildings")
        ]
        public_vp = json_int(player, "public_points")
        lines.append(
            f"{seat_label(seat)}: {json_int(player, 'doubloons')}d, "
            f"goods [{goods_text or 'none'}], "
            f"plantations [{', '.join(plantations) or 'none'}], "
            f"quarries {json_int(player, 'occupied_quarries')}/"
            f"{json_int(player, 'quarries')}, "
            f"buildings [{', '.join(buildings) or 'none'}], "
            f"colonists unplaced {json_int(player, 'colonists_unplaced')}, "
            f"public VP {public_vp}."
        )
    return lines


def final_lines(data: JsonObject) -> list[str]:
    final = data.get("final_scores")
    if not isinstance(final, list):
        return []
    lines = ["Final scores:"]
    for entry in final:
        if not isinstance(entry, dict):
            continue
        seat = PlayerId(json_int(entry, "player"))
        lines.append(
            f"  {seat_label(seat)}: {json_int(entry, 'points')} points "
            f"({json_int(entry, 'vp_chips')} chips)."
        )
    return lines


def _objects(data: JsonObject, key: str) -> list[JsonObject]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _object(data: JsonObject, key: str) -> JsonObject:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def describe_action(observation: Observation, action: Action) -> str:
    """One-line human description of an action."""
    match action:
        case SelectRole(role=role):
            return f"Choose the {role} role."
        case TakePlantation(good=good, use_hospice=use_hospice):
            return f"Take a face-up {good} plantation" + (
                "." if use_hospice else " without the Hospice colonist."
            )
        case TakeQuarry(use_hospice=use_hospice):
            return "Take a quarry" + (
                "." if use_hospice else " without the Hospice colonist."
            )
        case UseHacienda():
            return "Draw an extra plantation with the Hacienda."
        case Pass():
            return "Pass."
        case Build(building=building, use_university=use_university):
            return f"Build {building}" + (
                "." if use_university else " without the University colonist."
            )
        case ProducePrivilege(good=good):
            return f"Take an extra {good} as the Craftsman privilege."
        case Sell(good=good):
            return f"Sell one {good} to the trading house."
        case LoadShip(good=good, ship=ship):
            return f"Load {good} on cargo ship {ship + 1}."
        case LoadWharf(good=good):
            return f"Load {good} on your Wharf."
        case PlaceColonist(target="quarry"):
            return "Place a colonist on a quarry."
        case PlaceColonist(target=target, index=index):
            return f"Place a colonist on {target} {index}."
        case PickUpColonist(target="quarry"):
            return "Pick up a colonist from a quarry."
        case PickUpColonist(target=target, index=index):
            return f"Pick up a colonist from {target} {index}."
        case FinishPlacement():
            return "Finish placing colonists."
        case DiscardGoods(protected=protected, keep=keep, legacy=legacy):
            if legacy:
                return "Keep one of each type plus the warehouse-protected types."
            parts: list[str] = []
            if keep is not None:
                parts.append(f"keep 1 {keep}")
            if protected:
                parts.append(f"warehouse protects {', '.join(sorted(protected))}")
            return "Keep goods after shipping" + (
                f" ({'; '.join(parts)})." if parts else " (keep nothing)."
            )
    return "Take an action."


# Re-exported for type checkers; kept close to the rendering code.
__all__ = [
    "describe_action",
    "observe",
    "render_text",
]
