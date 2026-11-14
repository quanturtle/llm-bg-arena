"""Text notation for Terra Mystica actions: one canonical form, strict parsing."""

import re
from typing import Literal, cast

from boardgames.core import NotationError
from boardgames.games.terra_mystica.constants import (
    POWER_ACTION_KINDS,
    BuildingType,
    Cult,
    FactionType,
    PowerActionKind,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BonusSpade,
    BuildBridge,
    BuildDwelling,
    ChaosDoubleTurn,
    ChooseFaction,
    ChoosePowerGain,
    ChooseStrongholdPriests,
    ConversionKind,
    Convert,
    CultistCult,
    GiantsSpades,
    Hex,
    NomadsSandstorm,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    SpecialCult,
    SwarmlingsUpgrade,
    TakeBonusCard,
    TakeFavorTile,
    TakeTownTile,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
    WitchesRide,
)

HEX_TEXT = r"(-?[0-9]+),(-?[0-9]+)"
BUILD_PATTERN = re.compile(rf"build {HEX_TEXT}(?: river {HEX_TEXT})?")
TRANSFORM_PATTERN = re.compile(rf"transform {HEX_TEXT}(?: to ([a-z]+))?")
UPGRADE_PATTERN = re.compile(rf"upgrade {HEX_TEXT} ([a-z_]+)(?: river {HEX_TEXT})?")
PRIEST_PATTERN = re.compile(r"priest (fire|water|earth|air) ([0-3])")
ADVANCE_CULT_PATTERN = re.compile(r"advance (fire|water|earth|air)")
STRONGHOLD_PATTERN = re.compile(r"stronghold ([0-3])")
TOWN_PATTERN = re.compile(r"town ([0-7])")
FAVOR_PATTERN = re.compile(r"favor (0|1[01]|[0-9])")
POWER_PATTERN = re.compile(rf"power ({'|'.join(POWER_ACTION_KINDS)})")
CULT_SPADE_PATTERN = re.compile(rf"spade {HEX_TEXT}(?: to ([a-z]+))?")
BRIDGE_PATTERN = re.compile(rf"bridge {HEX_TEXT} {HEX_TEXT}(?: (workers))?")
CONVERT_PATTERN = re.compile(
    r"convert (power priest|power worker|power coin|priest worker|worker coin)"
)
FACTION_PATTERN = re.compile(r"faction ([a-z_]+)")
BONUS_PATTERN = re.compile(r"bonus ([0-8])")
SPECIAL_CULT_PATTERN = re.compile(r"special (auren|water|bonus) (fire|water|earth|air)")
CULTIST_PATTERN = re.compile(r"cultist (fire|water|earth|air)")
RIDE_PATTERN = re.compile(rf"ride {HEX_TEXT}")
SWARMLINGS_PATTERN = re.compile(rf"swarmlings {HEX_TEXT}")
GIANTS_PATTERN = re.compile(rf"giants {HEX_TEXT}")
SANDSTORM_PATTERN = re.compile(rf"sandstorm {HEX_TEXT}")

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
        case BuildBridge(first=first, second=second, payment=payment):
            suffix = " workers" if payment == "workers" else ""
            return f"bridge {first.notation()} {second.notation()}{suffix}"
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
        case Convert(kind=kind):
            return "convert " + kind.replace("_", " ")
        case ChoosePowerGain(accept=accept):
            return "gain power" if accept else "decline power"
        case ChooseFaction(faction=faction):
            return f"faction {faction.value}"
        case TakeBonusCard(index=index):
            return f"bonus {index}"
        case SpecialCult(source=source, cult=cult):
            short = "water" if source == "water_favor" else source
            return f"special {short} {cult.value}"
        case CultistCult(cult=cult):
            return f"cultist {cult.value}"
        case BonusSpade():
            return "special spade"
        case WitchesRide(position=position):
            return f"ride {position.notation()}"
        case SwarmlingsUpgrade(position=position):
            return f"swarmlings {position.notation()}"
        case ChaosDoubleTurn():
            return "double turn"
        case GiantsSpades(position=position):
            return f"giants {position.notation()}"
        case NomadsSandstorm(position=position):
            return f"sandstorm {position.notation()}"
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
    if text == "gain power":
        return ChoosePowerGain(True)
    if text == "decline power":
        return ChoosePowerGain(False)
    if text == "special spade":
        return BonusSpade()
    if text == "double turn":
        return ChaosDoubleTurn()

    if match := BUILD_PATTERN.fullmatch(text):
        river = (
            None
            if match.group(3) is None
            else parse_hex(match.group(3), match.group(4))
        )
        return BuildDwelling(parse_hex(match.group(1), match.group(2)), river=river)
    if match := BRIDGE_PATTERN.fullmatch(text):
        payment: Literal["power", "workers"] = "workers" if match.group(5) else "power"
        return BuildBridge(
            parse_hex(match.group(1), match.group(2)),
            parse_hex(match.group(3), match.group(4)),
            payment,
        )
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
    if match := CONVERT_PATTERN.fullmatch(text):
        kind = cast(ConversionKind, match.group(1).replace(" ", "_"))
        return Convert(kind)
    if match := FACTION_PATTERN.fullmatch(text):
        try:
            return ChooseFaction(FactionType(match.group(1)))
        except ValueError as error:
            raise NotationError(f"{text!r} does not name a faction") from error
    if match := BONUS_PATTERN.fullmatch(text):
        return TakeBonusCard(int(match.group(1)))
    if match := SPECIAL_CULT_PATTERN.fullmatch(text):
        source = match.group(1)
        special_source = "water_favor" if source == "water" else source
        return SpecialCult(
            cast(Literal["auren", "water_favor", "bonus"], special_source),
            Cult(match.group(2)),
        )
    if match := CULTIST_PATTERN.fullmatch(text):
        return CultistCult(Cult(match.group(1)))
    if match := RIDE_PATTERN.fullmatch(text):
        return WitchesRide(parse_hex(match.group(1), match.group(2)))
    if match := SWARMLINGS_PATTERN.fullmatch(text):
        return SwarmlingsUpgrade(parse_hex(match.group(1), match.group(2)))
    if match := GIANTS_PATTERN.fullmatch(text):
        return GiantsSpades(parse_hex(match.group(1), match.group(2)))
    if match := SANDSTORM_PATTERN.fullmatch(text):
        return NomadsSandstorm(parse_hex(match.group(1), match.group(2)))
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
