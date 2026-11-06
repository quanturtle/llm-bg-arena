"""Text notation for Terra Mystica actions: one canonical form, strict parsing."""

import re
from typing import cast

from boardgames.core import NotationError
from boardgames.games.terra_mystica.constants import (
    POWER_ACTION_KINDS,
    BuildingType,
    Cult,
    PowerActionKind,
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
    TakeFavorTile,
    TakeTownTile,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
)

HEX_TEXT = r"(-?[0-9]+),(-?[0-9]+)"
BUILD_PATTERN = re.compile(rf"build {HEX_TEXT}(?: river {HEX_TEXT})?")
TRANSFORM_PATTERN = re.compile(rf"transform {HEX_TEXT}(?: to ([a-z]+))?")
UPGRADE_PATTERN = re.compile(rf"upgrade {HEX_TEXT} ([a-z_]+)(?: river {HEX_TEXT})?")
PRIEST_PATTERN = re.compile(r"priest (fire|water|earth|air) ([0-3])")
ADVANCE_CULT_PATTERN = re.compile(r"advance (fire|water|earth|air)")
STRONGHOLD_PATTERN = re.compile(r"stronghold ([0-3])")
TOWN_PATTERN = re.compile(r"town ([0-4])")
FAVOR_PATTERN = re.compile(r"favor (0|1[01]|[0-9])")
POWER_PATTERN = re.compile(rf"power ({'|'.join(POWER_ACTION_KINDS)})")
CULT_SPADE_PATTERN = re.compile(rf"spade {HEX_TEXT}(?: to ([a-z]+))?")

BUILDINGS: frozenset[str] = frozenset(building.value for building in BuildingType)
TERRAINS: frozenset[str] = frozenset(
    terrain.value for terrain in Terrain if terrain is not Terrain.RIVER
)


def format_action(action: Action) -> str:
    """Canonical notation of an action."""
    match action:
        case BuildDwelling(position=position, river=river):
            suffix = "" if river is None else f" river {river.notation()}"
            return f"build {position.notation()}{suffix}"
        case TransformTerrain(position=position, to=terrain):
            suffix = "" if terrain is None else f" to {terrain.value}"
            return f"transform {position.notation()}{suffix}"
        case UpgradeBuilding(position=position, to=building, river=river):
            suffix = "" if river is None else f" river {river.notation()}"
            return f"upgrade {position.notation()} {building.value}{suffix}"
        case AdvanceShipping():
            return "shipping"
        case AdvanceDigging():
            return "digging"
        case SendPriest(cult=cult, order=order):
            return f"priest {cult.value} {order}"
        case AdvanceCult(cult=cult):
            return f"advance {cult.value}"
        case ChooseStrongholdPriests(workers=workers):
            return f"stronghold {workers}"
        case TakeTownTile(index=index):
            return f"town {index}"
        case TakeFavorTile(index=index):
            return f"favor {index}"
        case PowerAction(kind=kind):
            return f"power {kind}"
        case UseCultSpade(position=position, to=terrain):
            suffix = "" if terrain is None else f" to {terrain.value}"
            return f"spade {position.notation()}{suffix}"
        case SkipCultSpade():
            return "skip spade"
        case TradeVpForCoin():
            return "alchemist vp"
        case TradeCoinsForVp():
            return "alchemist coins"
        case Pass():
            return "pass"
    raise TypeError(f"unknown Terra Mystica action {action!r}")


def parse_action(text: str) -> Action:
    """Strict parse of notation; legality is checked separately."""
    if text == "shipping":
        return AdvanceShipping()
    if text == "digging":
        return AdvanceDigging()
    if text == "pass":
        return Pass()
    if text == "skip spade":
        return SkipCultSpade()

    if match := BUILD_PATTERN.fullmatch(text):
        river = (
            None
            if match.group(3) is None
            else parse_hex(match.group(3), match.group(4))
        )
        return BuildDwelling(parse_hex(match.group(1), match.group(2)), river=river)
    if match := TRANSFORM_PATTERN.fullmatch(text):
        terrain = parse_terrain(match.group(3))
        return TransformTerrain(parse_hex(match.group(1), match.group(2)), terrain)
    if match := UPGRADE_PATTERN.fullmatch(text):
        name = match.group(3)
        if name not in BUILDINGS:
            raise NotationError(f"{text!r} does not name a building")
        river = (
            None
            if match.group(4) is None
            else parse_hex(match.group(4), match.group(5))
        )
        return UpgradeBuilding(
            parse_hex(match.group(1), match.group(2)),
            BuildingType(name),
            river=river,
        )
    if match := PRIEST_PATTERN.fullmatch(text):
        cult, order = match.groups()
        return SendPriest(Cult(cult), int(order))
    if match := ADVANCE_CULT_PATTERN.fullmatch(text):
        return AdvanceCult(Cult(match.group(1)))
    if match := STRONGHOLD_PATTERN.fullmatch(text):
        return ChooseStrongholdPriests(int(match.group(1)))
    if match := TOWN_PATTERN.fullmatch(text):
        return TakeTownTile(int(match.group(1)))
    if match := FAVOR_PATTERN.fullmatch(text):
        return TakeFavorTile(int(match.group(1)))
    if match := POWER_PATTERN.fullmatch(text):
        return PowerAction(cast(PowerActionKind, match.group(1)))
    if match := CULT_SPADE_PATTERN.fullmatch(text):
        terrain = parse_terrain(match.group(3))
        return UseCultSpade(parse_hex(match.group(1), match.group(2)), terrain)
    if text == "alchemist vp":
        return TradeVpForCoin()
    if text == "alchemist coins":
        return TradeCoinsForVp()
    raise NotationError(f"{text!r} is not a Terra Mystica action")


def parse_hex(q_text: str, r_text: str) -> Hex:
    return Hex(int(q_text), int(r_text))


def parse_terrain(name: str | None) -> Terrain | None:
    if name is None:
        return None
    if name not in TERRAINS:
        raise NotationError(f"{name!r} is not a land terrain")
    return Terrain(name)
