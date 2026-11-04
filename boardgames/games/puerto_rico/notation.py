"""Text notation for Puerto Rico actions: one canonical form, strict parsing."""

import re
from typing import Literal, cast

from boardgames.core import NotationError
from boardgames.games.puerto_rico.constants import (
    BUILDINGS,
    GOODS,
    ROLE_NAMES,
    Good,
    Role,
)
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
ROLE_TEXT = "(" + "|".join(sorted(ROLE_NAMES, key=len, reverse=True)) + ")"
INDEX_TEXT = r"(0|[1-9][0-9]*)"
SHIP_TEXT = r"([1-3])"

ROLE_PATTERN = re.compile(rf"role {ROLE_TEXT}")
PLANTATION_PATTERN = re.compile(rf"take {GOOD_TEXT}( nohospice)?")
BUILD_PATTERN = re.compile(r"build ([a-z_]+)( nouniversity)?")
PRIVILEGE_PATTERN = re.compile(rf"privilege {GOOD_TEXT}")
SELL_PATTERN = re.compile(rf"sell {GOOD_TEXT}")
SHIP_PATTERN = re.compile(rf"ship {GOOD_TEXT} s{SHIP_TEXT}")
WHARF_PATTERN = re.compile(rf"wharf {GOOD_TEXT}")
PLACE_PATTERN = re.compile(rf"place (plantation|building) {INDEX_TEXT}")
PICK_PATTERN = re.compile(rf"pick (plantation|building) {INDEX_TEXT}")
DISCARD_PATTERN = re.compile(r"discard(?: (.+))?")


def format_action(action: Action) -> str:
    """Canonical notation of an action."""
    match action:
        case SelectRole(role=role):
            return f"role {role}"
        case TakePlantation(good=good, use_hospice=use_hospice):
            return f"take {good}" + ("" if use_hospice else " nohospice")
        case TakeQuarry(use_hospice=use_hospice):
            return "take quarry" + ("" if use_hospice else " nohospice")
        case UseHacienda():
            return "hacienda"
        case Pass():
            return "pass"
        case Build(building=building, use_university=use_university):
            return f"build {building}" + ("" if use_university else " nouniversity")
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
        case DiscardGoods(protected=protected, keep=keep):
            parts: list[str] = list(protected)
            parts.append("keep" if keep is not None else "none")
            if keep is not None:
                parts.append(keep)
            return f"discard {' '.join(parts)}"
    raise TypeError(f"unknown Puerto Rico action {action!r}")


def parse_action(text: str) -> Action:
    """Strict parse of notation; syntax only, legality is checked separately."""
    if text != text.strip() or "  " in text:
        raise NotationError(f"{text!r} is not canonical Puerto Rico notation")
    if text == "take quarry":
        return TakeQuarry()
    if text == "take quarry nohospice":
        return TakeQuarry(use_hospice=False)
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
        return SelectRole(cast(Role, match.group(1)))
    if match := PLANTATION_PATTERN.fullmatch(text):
        return TakePlantation(
            _good(match.group(1)),
            use_hospice=match.group(2) is None,
        )
    if match := BUILD_PATTERN.fullmatch(text):
        name = match.group(1)
        if name not in BUILDINGS:
            raise NotationError(f"{text!r} does not name a building")
        return Build(name, use_university=match.group(2) is None)
    if match := PRIVILEGE_PATTERN.fullmatch(text):
        return ProducePrivilege(_good(match.group(1)))
    if match := SELL_PATTERN.fullmatch(text):
        return Sell(_good(match.group(1)))
    if match := SHIP_PATTERN.fullmatch(text):
        return LoadShip(_good(match.group(1)), int(match.group(2)) - 1)
    if match := WHARF_PATTERN.fullmatch(text):
        return LoadWharf(_good(match.group(1)))
    if match := PLACE_PATTERN.fullmatch(text):
        return PlaceColonist(
            cast(Literal["plantation", "building"], match.group(1)),
            int(match.group(2)),
        )
    if match := PICK_PATTERN.fullmatch(text):
        return PickUpColonist(
            cast(Literal["plantation", "building"], match.group(1)),
            int(match.group(2)),
        )
    if match := DISCARD_PATTERN.fullmatch(text):
        return _discard(match.group(1))
    raise NotationError(f"{text!r} is not a Puerto Rico action")


def _good(text: str) -> Good:
    if text not in GOODS:
        raise NotationError(f"{text!r} names an unknown good")
    return text


def _discard(text: str | None) -> DiscardGoods:
    tokens = text.split(" ") if text else []
    if "keep" in tokens:
        if "none" in tokens:
            raise NotationError("discard cannot both keep a good and keep none")
        index = tokens.index("keep")
        if index != len(tokens) - 2:
            raise NotationError("discard ends with keep and one good")
        protected_tokens = tokens[:index]
        keep: Good | None = _good(tokens[-1])
    else:
        if not tokens or tokens[-1] != "none" or tokens.count("none") != 1:
            raise NotationError("discard ends with none or keep and one good")
        protected_tokens = tokens[:-1]
        keep = None
    if len(set(protected_tokens)) != len(protected_tokens):
        raise NotationError("discard names each protected good once")
    protected = tuple(
        sorted((_good(token) for token in protected_tokens), key=GOODS.index)
    )
    return DiscardGoods(protected, keep)
