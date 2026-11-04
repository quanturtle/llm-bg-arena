"""Text notation for Terra Mystica actions: one canonical form, strict parsing."""

import re

from boardgames.core import NotationError
from boardgames.games.terra_mystica.constants import BuildingType, Cult
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BuildDwelling,
    Hex,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
)

HEX_TEXT = r"(-?[0-9]+),(-?[0-9]+)"
BUILD_PATTERN = re.compile(rf"build {HEX_TEXT}")
TRANSFORM_PATTERN = re.compile(rf"transform {HEX_TEXT}")
UPGRADE_PATTERN = re.compile(rf"upgrade {HEX_TEXT} ([a-z_]+)")
PRIEST_PATTERN = re.compile(r"priest (fire|water|earth|air) ([0-3])")
ADVANCE_CULT_PATTERN = re.compile(r"advance (fire|water|earth|air)")
POWER_PATTERN = re.compile(r"power (priest|workers|coins)")
CULT_SPADE_PATTERN = re.compile(rf"spade {HEX_TEXT}")
SKIP_CULT_SPADE_PATTERN = re.compile(r"skip spade")

BUILDINGS: frozenset[str] = frozenset(building.value for building in BuildingType)
CULTS: frozenset[str] = frozenset(cult.value for cult in Cult)


def format_action(action: Action) -> str:
    """Canonical notation of an action."""
    match action:
        case BuildDwelling(position=position):
            return f"build {position.notation()}"
        case TransformTerrain(position=position):
            return f"transform {position.notation()}"
        case UpgradeBuilding(position=position, to=building):
            return f"upgrade {position.notation()} {building.value}"
        case AdvanceShipping():
            return "shipping"
        case AdvanceDigging():
            return "digging"
        case SendPriest(cult=cult, order=order):
            return f"priest {cult.value} {order}"
        case AdvanceCult(cult=cult):
            return f"advance {cult.value}"
        case PowerAction(kind=kind):
            return f"power {kind}"
        case UseCultSpade(position=position):
            return f"spade {position.notation()}"
        case SkipCultSpade():
            return "skip spade"
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
        return BuildDwelling(parse_hex(match.group(1), match.group(2)))
    if match := TRANSFORM_PATTERN.fullmatch(text):
        return TransformTerrain(parse_hex(match.group(1), match.group(2)))
    if match := UPGRADE_PATTERN.fullmatch(text):
        name = match.group(3)
        if name not in BUILDINGS:
            raise NotationError(f"{text!r} does not name a building")
        return UpgradeBuilding(
            parse_hex(match.group(1), match.group(2)),
            BuildingType(name),
        )
    if match := PRIEST_PATTERN.fullmatch(text):
        cult, order = match.groups()
        if cult not in CULTS:
            raise NotationError(f"{text!r} does not name a cult")
        return SendPriest(Cult(cult), int(order))
    if match := ADVANCE_CULT_PATTERN.fullmatch(text):
        cult = match.group(1)
        if cult not in CULTS:
            raise NotationError(f"{text!r} does not name a cult")
        return AdvanceCult(Cult(cult))
    if match := POWER_PATTERN.fullmatch(text):
        kind = match.group(1)
        return PowerAction(kind)  # type: ignore[arg-type]
    if match := CULT_SPADE_PATTERN.fullmatch(text):
        return UseCultSpade(parse_hex(match.group(1), match.group(2)))
    raise NotationError(f"{text!r} is not a Terra Mystica action")


def parse_hex(q_text: str, r_text: str) -> Hex:
    return Hex(int(q_text), int(r_text))
