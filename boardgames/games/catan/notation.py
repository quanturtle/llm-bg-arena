"""Text notation for Catan actions: one canonical form, strict parsing."""

import re
from typing import cast

from boardgames.core import NotationError, PlayerId, seat_label
from boardgames.games.catan.model import (
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    BuyDev,
    DeclineOffer,
    DevCard,
    Discard,
    EndTurn,
    MoveRobber,
    OfferTrade,
    PlaceRoad,
    PlaceSettlement,
    PlayKnight,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
    Resource,
    Roll,
)

RESOURCE_TEXT = r"(wood|brick|sheep|wheat|ore)"
NUMBER_TEXT = r"(0|[1-9][0-9]*)"
POSITIVE_TEXT = r"([1-9][0-9]*)"
PLAYER_TEXT = r"P([1-9][0-9]*)"

SETTLE_PATTERN = re.compile(rf"settle v{NUMBER_TEXT}")
ROAD_PATTERN = re.compile(rf"road e{NUMBER_TEXT}")
CITY_PATTERN = re.compile(rf"city v{NUMBER_TEXT}")
BANK_PATTERN = re.compile(
    rf"bank {POSITIVE_TEXT} {RESOURCE_TEXT} for 1 {RESOURCE_TEXT}"
)
OFFER_PATTERN = re.compile(
    rf"offer {RESOURCE_TEXT} for {RESOURCE_TEXT} to {PLAYER_TEXT}"
)
ROBBER_PATTERN = re.compile(rf"robber h{NUMBER_TEXT}(?: {PLAYER_TEXT})?")
KNIGHT_PATTERN = re.compile(rf"play knight h{NUMBER_TEXT}(?: {PLAYER_TEXT})?")
YEAR_PATTERN = re.compile(rf"play yearofplenty {RESOURCE_TEXT} {RESOURCE_TEXT}")
MONOPOLY_PATTERN = re.compile(rf"play monopoly {RESOURCE_TEXT}")
DISCARD_PATTERN = re.compile(rf"discard {RESOURCE_TEXT}")

# Development cards as notation spells them, for renders and rules text.
DEV_CARD_NOTATION: dict[DevCard, str] = {
    "knight": "knight",
    "road_building": "roadbuilding",
    "year_of_plenty": "yearofplenty",
    "monopoly": "monopoly",
    "victory_point": "victorypoint",
}


def format_action(action: Action) -> str:
    """Canonical notation of an action."""
    match action:
        case Roll():
            return "roll"
        case EndTurn():
            return "end turn"
        case PlaceSettlement(vertex=vertex):
            return f"settle v{vertex}"
        case PlaceRoad(edge=edge):
            return f"road e{edge}"
        case BuildCity(vertex=vertex):
            return f"city v{vertex}"
        case BuyDev():
            return "dev"
        case Discard(resource=resource):
            return f"discard {resource}"
        case MoveRobber(hex=hex_id, victim=victim):
            return robber_text("robber", hex_id, victim)
        case BankTrade(give=give, give_count=count, take=take):
            return f"bank {count} {give} for 1 {take}"
        case OfferTrade(give=give, take=take, target=target):
            return f"offer {give} for {take} to {seat_label(target)}"
        case AcceptOffer():
            return "accept"
        case DeclineOffer():
            return "decline"
        case PlayKnight(hex=hex_id, victim=victim):
            return robber_text("play knight", hex_id, victim)
        case PlayRoadBuilding():
            return "play roadbuilding"
        case PlayYearOfPlenty(first=first, second=second):
            return f"play yearofplenty {first} {second}"
        case PlayMonopoly(resource=resource):
            return f"play monopoly {resource}"
    raise TypeError(f"unknown Catan action {action!r}")


def robber_text(prefix: str, hex_id: int, victim: PlayerId | None) -> str:
    """Robber or knight notation, with an optional victim."""
    text = f"{prefix} h{hex_id}"
    return text if victim is None else f"{text} {seat_label(victim)}"


def parse_action(text: str) -> Action:
    """Strict parse of notation; syntax only, legality is checked separately."""
    if text == "roll":
        return Roll()
    if text == "end turn":
        return EndTurn()
    if text == "dev":
        return BuyDev()
    if text == "accept":
        return AcceptOffer()
    if text == "decline":
        return DeclineOffer()
    if text == "play roadbuilding":
        return PlayRoadBuilding()

    if match := SETTLE_PATTERN.fullmatch(text):
        return PlaceSettlement(int(match.group(1)))
    if match := ROAD_PATTERN.fullmatch(text):
        return PlaceRoad(int(match.group(1)))
    if match := CITY_PATTERN.fullmatch(text):
        return BuildCity(int(match.group(1)))
    if match := BANK_PATTERN.fullmatch(text):
        return BankTrade(
            cast(Resource, match.group(2)),
            int(match.group(1)),
            cast(Resource, match.group(3)),
        )
    if match := OFFER_PATTERN.fullmatch(text):
        return OfferTrade(
            cast(Resource, match.group(1)),
            cast(Resource, match.group(2)),
            PlayerId(int(match.group(3)) - 1),
        )
    if match := ROBBER_PATTERN.fullmatch(text):
        return MoveRobber(int(match.group(1)), player_or_none(match.group(2)))
    if match := KNIGHT_PATTERN.fullmatch(text):
        return PlayKnight(int(match.group(1)), player_or_none(match.group(2)))
    if match := YEAR_PATTERN.fullmatch(text):
        return PlayYearOfPlenty(
            cast(Resource, match.group(1)),
            cast(Resource, match.group(2)),
        )
    if match := MONOPOLY_PATTERN.fullmatch(text):
        return PlayMonopoly(cast(Resource, match.group(1)))
    if match := DISCARD_PATTERN.fullmatch(text):
        return Discard(cast(Resource, match.group(1)))
    raise NotationError(f"{text!r} is not a Catan action")


def player_or_none(text: str | None) -> PlayerId | None:
    """Parse a Pn token, or None when absent."""
    return None if text is None else PlayerId(int(text) - 1)
