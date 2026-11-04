"""Immutable data model for Catan: resources, actions, state and scoring."""

from dataclasses import dataclass
from typing import Literal, NewType, cast

from boardgames.core import PlayerId, Rng

type Resource = Literal["wood", "brick", "sheep", "wheat", "ore"]
type Terrain = Literal["forest", "pasture", "fields", "hills", "mountains", "desert"]
type DevCard = Literal[
    "knight", "road_building", "year_of_plenty", "monopoly", "victory_point"
]
type BuildingKind = Literal["settlement", "city"]
type Phase = Literal[
    "setup_settlement",
    "setup_road",
    "roll",
    "discard",
    "move_robber",
    "actions",
    "free_road",
    "trade_response",
    "game_over",
]
type Five = tuple[int, int, int, int, int]
Hand = NewType("Hand", Five)
DevHand = NewType("DevHand", Five)

RESOURCES: tuple[Resource, ...] = ("wood", "brick", "sheep", "wheat", "ore")
RESOURCE_INDEX = {resource: index for index, resource in enumerate(RESOURCES)}

DEV_CARDS: tuple[DevCard, ...] = (
    "knight",
    "road_building",
    "year_of_plenty",
    "monopoly",
    "victory_point",
)
DEV_INDEX = {card: index for index, card in enumerate(DEV_CARDS)}
DEV_DECK_COUNTS: tuple[DevCard, ...] = (
    ("knight",) * 14
    + ("road_building",) * 2
    + ("year_of_plenty",) * 2
    + ("monopoly",) * 2
    + ("victory_point",) * 5
)

TERRAIN_RESOURCE: dict[Terrain, Resource | None] = {
    "forest": "wood",
    "pasture": "sheep",
    "fields": "wheat",
    "hills": "brick",
    "mountains": "ore",
    "desert": None,
}
TERRAIN_DECK: tuple[Terrain, ...] = (
    "forest",
    "forest",
    "forest",
    "forest",
    "pasture",
    "pasture",
    "pasture",
    "pasture",
    "fields",
    "fields",
    "fields",
    "fields",
    "hills",
    "hills",
    "hills",
    "mountains",
    "mountains",
    "mountains",
    "desert",
)
NUMBER_TOKENS: tuple[int, ...] = (
    2,
    3,
    3,
    4,
    4,
    5,
    5,
    6,
    6,
    8,
    8,
    9,
    9,
    10,
    10,
    11,
    11,
    12,
)
# The most frequent rolls; their tokens are printed red and never touch.
RED_NUMBERS: tuple[int, ...] = (6, 8)

ROAD_COST: Hand = Hand((1, 1, 0, 0, 0))
SETTLEMENT_COST: Hand = Hand((1, 1, 1, 1, 0))
CITY_COST: Hand = Hand((0, 0, 0, 2, 3))
DEV_COST: Hand = Hand((0, 0, 1, 1, 1))

MAX_ROADS = 15
MAX_SETTLEMENTS = 5
MAX_CITIES = 4
LONGEST_ROAD_MINIMUM = 5
LARGEST_ARMY_MINIMUM = 3
DISCARD_THRESHOLD = 7


@dataclass(frozen=True)
class CatanConfig:
    """Standard 19-hex Catan for 3 or 4 players, with a configurable VP goal.

    `max_offers_per_turn` keeps trade talks from stalling a match; 0 allows
    unlimited offers.
    """

    num_players: int = 4
    victory_points: int = 10
    max_offers_per_turn: int = 3


@dataclass(frozen=True)
class Roll:
    """Roll the two dice and start the turn's action phase."""


@dataclass(frozen=True)
class EndTurn:
    """End the current player's turn."""


@dataclass(frozen=True)
class PlaceSettlement:
    """Place a settlement on an empty intersection, during setup or later."""

    vertex: int


@dataclass(frozen=True)
class PlaceRoad:
    """Place a road on an empty path, during setup or later."""

    edge: int


@dataclass(frozen=True)
class BuildCity:
    """Upgrade one of your settlements to a city."""

    vertex: int


@dataclass(frozen=True)
class BuyDev:
    """Buy the top development card."""


@dataclass(frozen=True)
class Discard:
    """Discard one resource card after a 7."""

    resource: Resource


@dataclass(frozen=True)
class MoveRobber:
    """Move the robber after a 7; steal from `victim` if anyone is eligible."""

    hex: int
    victim: PlayerId | None


@dataclass(frozen=True)
class BankTrade:
    """Trade `give_count` copies of one resource for one of another."""

    give: Resource
    give_count: int
    take: Resource


@dataclass(frozen=True)
class OfferTrade:
    """Offer one card of one resource to another player for one card back."""

    give: Resource
    take: Resource
    target: PlayerId


@dataclass(frozen=True)
class AcceptOffer:
    """Accept the pending trade offer."""


@dataclass(frozen=True)
class DeclineOffer:
    """Decline the pending trade offer."""


@dataclass(frozen=True)
class PlayKnight:
    """Play a knight: move the robber and steal, if anyone is eligible."""

    hex: int
    victim: PlayerId | None


@dataclass(frozen=True)
class PlayRoadBuilding:
    """Play Road Building: place two free roads."""


@dataclass(frozen=True)
class PlayYearOfPlenty:
    """Play Year of Plenty: take two resource cards from the bank."""

    first: Resource
    second: Resource

    def __post_init__(self) -> None:
        """Keep the pair in resource order so equal choices share one notation."""
        first, second = self.first, self.second
        if RESOURCE_INDEX[first] > RESOURCE_INDEX[second]:
            object.__setattr__(self, "first", second)
            object.__setattr__(self, "second", first)


@dataclass(frozen=True)
class PlayMonopoly:
    """Play Monopoly: take every card of one resource from the others."""

    resource: Resource


type Action = (
    Roll
    | EndTurn
    | PlaceSettlement
    | PlaceRoad
    | BuildCity
    | BuyDev
    | Discard
    | MoveRobber
    | BankTrade
    | OfferTrade
    | AcceptOffer
    | DeclineOffer
    | PlayKnight
    | PlayRoadBuilding
    | PlayYearOfPlenty
    | PlayMonopoly
)


@dataclass(frozen=True)
class Hex:
    """One board hex: its terrain and number token (None on the desert)."""

    terrain: Terrain
    number: int | None


@dataclass(frozen=True)
class Port:
    """A harbour on a coastal path; `resource` None is a generic 3:1 port."""

    edge: int
    resource: Resource | None


@dataclass(frozen=True)
class Building:
    """A settlement or city owned by a player."""

    player: PlayerId
    kind: BuildingKind


@dataclass(frozen=True)
class Offer:
    """An open one-for-one trade offer."""

    from_player: PlayerId
    to_player: PlayerId
    give: Resource
    take: Resource


@dataclass(frozen=True)
class CatanState:
    """Full game state. Hands, development cards and the deck are hidden."""

    config: CatanConfig
    rng: Rng
    hexes: tuple[Hex, ...]
    ports: tuple[Port, ...]
    robber: int
    dev_deck: tuple[DevCard, ...]
    turn: int
    active: PlayerId
    phase: Phase
    setup_index: int
    setup_vertex: int | None
    buildings: tuple[Building | None, ...]
    roads: tuple[PlayerId | None, ...]
    hands: tuple[Hand, ...]
    dev_hands: tuple[DevHand, ...]
    knights_played: tuple[int, ...]
    longest_road: PlayerId | None
    largest_army: PlayerId | None
    dev_bought: DevHand
    dev_played_this_turn: bool
    free_roads: int
    offers_this_turn: int
    discard_remaining: tuple[int, ...]
    dice: tuple[int, int] | None
    pending_offer: Offer | None
    winner: PlayerId | None


def empty_hand() -> Hand:
    """Five zeroes, one per resource."""
    return Hand((0, 0, 0, 0, 0))


def empty_dev_hand() -> DevHand:
    """Five zeroes, one per development-card type."""
    return DevHand((0, 0, 0, 0, 0))


def hand_from(**counts: int) -> Hand:
    """Build a hand from named resources, for tests and setup."""
    return Hand(cast(Five, tuple(counts.get(resource, 0) for resource in RESOURCES)))


def dev_hand_from(**counts: int) -> DevHand:
    """Build a development-card hand from named cards, for tests and setup."""
    return DevHand(cast(Five, tuple(counts.get(card, 0) for card in DEV_CARDS)))


def hand_total(hand: Hand | DevHand) -> int:
    """Number of cards in a hand."""
    return sum(hand)


def hand_get(hand: Hand, resource: Resource) -> int:
    """Cards of one resource in a hand."""
    return hand[RESOURCE_INDEX[resource]]


def dev_get(hand: DevHand, card: DevCard) -> int:
    """Copies of one development card in a hand."""
    return hand[DEV_INDEX[card]]


def hand_plus(first: Hand, second: Hand) -> Hand:
    """Sum of two hands."""
    return cast(Hand, tuple(a + b for a, b in zip(first, second, strict=True)))


def hand_minus(hand: Hand, cost: Hand) -> Hand | None:
    """`hand - cost`, or None when a card is missing."""
    if any(have < need for have, need in zip(hand, cost, strict=True)):
        return None
    return cast(Hand, tuple(have - need for have, need in zip(hand, cost, strict=True)))


def hand_with(hand: Hand, resource: Resource, count: int = 1) -> Hand:
    """A hand with `count` more or fewer cards of one resource."""
    values = list(hand)
    updated = values[RESOURCE_INDEX[resource]] + count
    if updated < 0:
        raise ValueError(f"cannot remove {resource} from a hand that lacks it")
    values[RESOURCE_INDEX[resource]] = updated
    return Hand(cast(Five, tuple(values)))


def dev_with(hand: DevHand, card: DevCard, count: int = 1) -> DevHand:
    """A development-card hand with `count` more or fewer of one type."""
    values = list(hand)
    updated = values[DEV_INDEX[card]] + count
    if updated < 0:
        raise ValueError(f"cannot remove {card} from a hand that lacks it")
    values[DEV_INDEX[card]] = updated
    return DevHand(cast(Five, tuple(values)))


def dev_minus(hand: DevHand, cost: DevHand) -> DevHand | None:
    """`hand - cost`, or None when a development card is missing."""
    if any(have < need for have, need in zip(hand, cost, strict=True)):
        return None
    return DevHand(
        cast(Five, tuple(have - need for have, need in zip(hand, cost, strict=True)))
    )


def playable_dev_hand(state: CatanState, player: PlayerId) -> DevHand:
    """Development cards owned before this turn, which may still be played."""
    return dev_minus(state.dev_hands[player], state.dev_bought) or empty_dev_hand()


def hand_cards(hand: Hand) -> list[Resource]:
    """The hand expanded into individual cards, in resource order."""
    cards: list[Resource] = []
    for resource, count in zip(RESOURCES, hand, strict=True):
        cards.extend([resource] * count)
    return cards


def hand_json(hand: Hand) -> dict[str, int]:
    """The hand as a JSON object keyed by resource."""
    return {resource: count for resource, count in zip(RESOURCES, hand, strict=True)}


def dev_hand_json(hand: DevHand) -> dict[str, int]:
    """Development cards as a JSON object keyed by card type."""
    return {card: count for card, count in zip(DEV_CARDS, hand, strict=True)}


def can_afford(hand: Hand, cost: Hand) -> bool:
    """Whether a hand holds every card of a cost."""
    return all(have >= need for have, need in zip(hand, cost, strict=True))


def building_counts(state: CatanState, player: PlayerId) -> tuple[int, int]:
    """Settlements and cities on the board for one player."""
    settlements = 0
    cities = 0
    for building in state.buildings:
        if building is None or building.player != player:
            continue
        if building.kind == "settlement":
            settlements += 1
        else:
            cities += 1
    return settlements, cities


def road_count(state: CatanState, player: PlayerId) -> int:
    """Roads on the board for one player."""
    return sum(1 for owner in state.roads if owner == player)


def point_breakdown(
    state: CatanState, player: PlayerId, *, include_hidden: bool
) -> dict[str, float]:
    """Victory points by source; hidden victory cards excluded for opponents."""
    settlements, cities = building_counts(state, player)
    victory_cards = (
        dev_get(state.dev_hands[player], "victory_point") if include_hidden else 0
    )
    return {
        "settlements": float(settlements),
        "cities": float(2 * cities),
        "victory cards": float(victory_cards),
        "longest road": 2.0 if state.longest_road == player else 0.0,
        "largest army": 2.0 if state.largest_army == player else 0.0,
    }


def total_points(
    state: CatanState, player: PlayerId, *, include_hidden: bool = True
) -> float:
    """Total victory points for one player."""
    return sum(point_breakdown(state, player, include_hidden=include_hidden).values())
