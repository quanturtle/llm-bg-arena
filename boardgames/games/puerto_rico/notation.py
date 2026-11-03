"""Text notation for Puerto Rico actions: one canonical form, strict parsing."""

import re

from boardgames.core import NotationError
from boardgames.games.puerto_rico.constants import BUILDINGS, GOODS, Role
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
    SelectRole,
    Sell,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
)

GOOD_TEXT = r"(corn|indigo|sugar|tobacco|coffee)"
ROLE_TEXT = r"(settler|mayor|builder|craftsman|trader|captain|prospector_2|prospector)"
INDEX_TEXT = r"(0|[1-9][0-9]*)"
SHIP_TEXT = r"([1-3])"

ROLE_PATTERN = re.compile(rf"role {ROLE_TEXT}")
PLANTATION_PATTERN = re.compile(rf"take {GOOD_TEXT}")
QUARRY_PATTERN = re.compile(r"take quarry")
HACIENDA_PATTERN = re.compile(r"hacienda")
PASS_PATTERN = re.compile(r"pass")
BUILD_PATTERN = re.compile(r"build ([a-z_]+)")
PRIVILEGE_PATTERN = re.compile(rf"privilege {GOOD_TEXT}")
SELL_PATTERN = re.compile(rf"sell {GOOD_TEXT}")
SHIP_PATTERN = re.compile(rf"ship {GOOD_TEXT} s{SHIP_TEXT}")
WHARF_PATTERN = re.compile(rf"wharf {GOOD_TEXT}")
PLACE_PATTERN = re.compile(rf"place (plantation|building) {INDEX_TEXT}")
PLACE_QUARRY_PATTERN = re.compile(r"place quarry")
PICK_PATTERN = re.compile(rf"pick (plantation|building) {INDEX_TEXT}")
PICK_QUARRY_PATTERN = re.compile(r"pick quarry")
FINISH_PATTERN = re.compile(r"finish")
DISCARD_PATTERN = re.compile(r"discard(?: (.+))?")


def format_action(action: Action) -> str:
    """Canonical notation of an action."""
    match action:
        case SelectRole(role=role):
            return f"role {role}"
        case TakePlantation(good=good):
            return f"take {good}"
        case TakeQuarry():
            return "take quarry"
        case UseHacienda():
            return "hacienda"
        case Pass():
            return "pass"
        case Build(building=building):
            return f"build {building}"
        case ProducePrivilege(good=good):
            return f"privilege {good}"
        case Sell(good=good):
            return f"sell {good}"
        case LoadShip(good=good, ship=ship):
            return f"ship {good} s{ship + 1}"
        case LoadWharf(good=good):
            return f"wharf {good}"
        case PlaceColonist(target="quarry"):
            return "place quarry"
        case PlaceColonist(target=target, index=index):
            return f"place {target} {index}"
        case PickUpColonist(target="quarry"):
            return "pick quarry"
        case PickUpColonist(target=target, index=index):
            return f"pick {target} {index}"
        case FinishPlacement():
            return "finish"
        case DiscardGoods(protected=protected):
            return "discard" if not protected else f"discard {' '.join(protected)}"
    raise TypeError(f"unknown Puerto Rico action {action!r}")


def parse_action(text: str) -> Action:
    """Strict parse of notation; syntax only, legality is checked separately."""
    if text == "take quarry":
        return TakeQuarry()
    if text == "hacienda":
        return UseHacienda()
    if text == "pass":
        return Pass()
    if text == "place quarry":
        return PlaceColonist("quarry")
    if text == "pick quarry":
        return PickUpColonist("quarry")
    if text == "finish":
        return FinishPlacement()

    if match := ROLE_PATTERN.fullmatch(text):
        role = match.group(1)
        if role not in ROLE_NAMES:
            raise NotationError(f"{text!r} is not a Puerto Rico role")
        return SelectRole(role)
    if match := PLANTATION_PATTERN.fullmatch(text):
        return TakePlantation(match.group(1))  # type: ignore[arg-type]
    if match := BUILD_PATTERN.fullmatch(text):
        name = match.group(1)
        if name not in BUILDINGS:
            raise NotationError(f"{text!r} does not name a building")
        return Build(name)
    if match := PRIVILEGE_PATTERN.fullmatch(text):
        return ProducePrivilege(match.group(1))  # type: ignore[arg-type]
    if match := SELL_PATTERN.fullmatch(text):
        return Sell(match.group(1))  # type: ignore[arg-type]
    if match := SHIP_PATTERN.fullmatch(text):
        return LoadShip(match.group(1), int(match.group(2)) - 1)  # type: ignore[arg-type]
    if match := WHARF_PATTERN.fullmatch(text):
        return LoadWharf(match.group(1))  # type: ignore[arg-type]
    if match := PLACE_PATTERN.fullmatch(text):
        target = match.group(1)
        if target not in ("plantation", "building"):
            raise NotationError(f"{text!r} does not name a target")
        return PlaceColonist(target, int(match.group(2)))  # type: ignore[arg-type]
    if match := PICK_PATTERN.fullmatch(text):
        target = match.group(1)
        if target not in ("plantation", "building"):
            raise NotationError(f"{text!r} does not name a target")
        return PickUpColonist(target, int(match.group(2)))  # type: ignore[arg-type]
    if match := DISCARD_PATTERN.fullmatch(text):
        protected_text = match.group(1)
        if not protected_text:
            return DiscardGoods()
        protected = tuple(protected_text.split(" "))
        for good in protected:
            if good not in GOODS:
                raise NotationError(f"{text!r} names an unknown good")
        return DiscardGoods(protected)
    raise NotationError(f"{text!r} is not a Puerto Rico action")


ROLE_NAMES: frozenset[Role] = frozenset(
    (
        "settler",
        "mayor",
        "builder",
        "craftsman",
        "trader",
        "captain",
        "prospector",
        "prospector_2",
    )
)
