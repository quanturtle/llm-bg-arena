"""Sealed auction: a small original game with chance, secrets and simultaneous bids.

Players bid coins in secret for a sequence of lots; lots in a player's secret
color score double. It exists to exercise the harness: a shuffled deck, die-roll
tie breaks, private information and decisions made by every player at once.
"""

import re
from dataclasses import dataclass, replace
from functools import partial
from importlib.resources import files
from typing import ClassVar, Literal

from boardgames.core import (
    ConfigError,
    Decision,
    Event,
    FlatActionSpace,
    IllegalActionError,
    JsonObject,
    JsonValue,
    NotationError,
    Observation,
    PlayerId,
    Rng,
    Scores,
    Transition,
    register_game,
    seat_label,
    seats,
)
from boardgames.core.actions import ActionSpace
from boardgames.core.json_data import (
    json_int,
    json_list_of,
    json_optional_int,
    json_str,
    json_str_list,
    json_str_lists,
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)

type Color = Literal["red", "green", "blue"]

COLORS: tuple[Color, ...] = ("red", "green", "blue")
LOT_VALUES = (1, 2, 3, 4)
MAX_COINS = 99
BID_PATTERN = re.compile(r"bid (0|[1-9][0-9]*)")


@dataclass(frozen=True)
class SealedAuctionConfig:
    """`lots` lots are sold, one per round; each player starts with `starting_coins`."""

    num_players: int = 3
    lots: int = 6
    starting_coins: int = 10


@dataclass(frozen=True)
class Lot:
    color: Color
    value: int

    def __str__(self) -> str:
        return f"{self.color} {self.value}"


@dataclass(frozen=True)
class Bid:
    """Bid `coins` for the current lot; 0 passes."""

    coins: int


@dataclass(frozen=True)
class SealedAuctionState:
    """Full state; `deck`, `secret_colors`, `bids` and `rng` are hidden from players.

    `current` is the lot up for auction, or None once the game is over.
    """

    config: SealedAuctionConfig
    rng: Rng
    deck: tuple[Lot, ...]
    current: Lot | None
    round: int
    coins: tuple[int, ...]
    won: tuple[tuple[Lot, ...], ...]
    secret_colors: tuple[Color, ...]
    bids: tuple[int | None, ...]


@register_game
class SealedAuction:
    """Sealed-bid auction for 2 to 4 players."""

    id: ClassVar[str] = "sealed_auction"

    def parse_config(self, raw: JsonObject) -> SealedAuctionConfig:
        config = dataclass_from_json(SealedAuctionConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: SealedAuctionConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    def setup(
        self, config: SealedAuctionConfig, seed: int
    ) -> Transition[SealedAuctionState]:
        rng = Rng.seeded(seed)
        full_deck = tuple(Lot(color, value) for color in COLORS for value in LOT_VALUES)
        deck, rng = rng.shuffled(full_deck)
        secret_colors, rng = deal_colors(rng, config.num_players)
        state = SealedAuctionState(
            config=config,
            rng=rng,
            deck=deck[1 : config.lots],
            current=deck[0],
            round=1,
            coins=(config.starting_coins,) * config.num_players,
            won=((),) * config.num_players,
            secret_colors=secret_colors,
            bids=(None,) * config.num_players,
        )
        started = Event(
            "started",
            f"Sealed auction: {config.num_players} players, {config.lots} lots, "
            f"{config.starting_coins} coins each.",
            to_json_object(config),
        )
        return Transition(
            state, (started, *color_events(secret_colors), lot_event(state))
        )

    def pending_decisions(self, state: SealedAuctionState) -> tuple[Decision, ...]:
        if state.current is None:
            return ()
        prompt = f"Bid coins for {state.current}, from 0 up to your coins."
        return tuple(
            Decision(player, "bid", prompt)
            for player in seats(state.config.num_players)
            if state.bids[player] is None
        )

    def legal_actions(
        self, state: SealedAuctionState, decision: Decision
    ) -> ActionSpace[Bid]:
        bids = [Bid(coins) for coins in range(state.coins[decision.player] + 1)]
        return FlatActionSpace(
            bids,
            bid_notation,
            explain=partial(explain_bid, state, decision.player),
            default=Bid(0),
        )

    def apply(
        self, state: SealedAuctionState, player: PlayerId, action: Bid
    ) -> Transition[SealedAuctionState]:
        check_bid(state, player, action)
        bids = (*state.bids[:player], action.coins, *state.bids[player + 1 :])
        state = replace(state, bids=bids)
        submitted = Event(
            "bid_submitted",
            f"{seat_label(player)} submitted a sealed bid.",
            {"player": player},
        )
        if any(bid is None for bid in bids):
            return Transition(state, (submitted,))
        resolved = resolve_round(state)
        return Transition(resolved.state, (submitted, *resolved.events))

    def is_terminal(self, state: SealedAuctionState) -> bool:
        return state.current is None

    def scores(self, state: SealedAuctionState) -> Scores:
        breakdown = {
            player: score_breakdown(state, player)
            for player in seats(state.config.num_players)
        }
        points = {player: sum(parts.values()) for player, parts in breakdown.items()}
        return Scores(points, breakdown)

    def observe(
        self, state: SealedAuctionState, viewer: PlayerId | None
    ) -> Observation:
        is_over = state.current is None
        players = seats(state.config.num_players)
        data: dict[str, JsonValue] = {
            "round": state.round,
            "total_rounds": state.config.lots,
            "current_lot": None if state.current is None else str(state.current),
            "coins": list(state.coins),
            "won": [[str(lot) for lot in lots] for lots in state.won],
            "has_bid": [state.bids[player] is not None for player in players],
            "your_color": None if viewer is None else state.secret_colors[viewer],
            "your_bid": None if viewer is None else state.bids[viewer],
            "revealed_colors": list(state.secret_colors) if is_over else None,
        }
        return Observation(viewer, data)

    def render_text(self, observation: Observation) -> str:
        data = observation.data
        coins = [str(count) for count in json_list_of(data, "coins", int)]
        won = [", ".join(lots) or "none" for lots in json_str_lists(data, "won")]
        return "\n".join(
            [
                round_line(data),
                *viewer_lines(observation.viewer, data),
                f"Coins: {per_player(coins)}.",
                f"Won lots: {per_player(won)}.",
                f"Bids this round: {bid_status(data)}.",
                *revealed_lines(data),
                "Scoring: lot values, doubled for your secret color, "
                "plus 1 point per 2 coins left.",
            ]
        )

    def rules_text(self) -> str:
        rules = files("boardgames.games.sealed_auction") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Bid) -> str:
        return bid_notation(action)

    def parse_action(self, text: str) -> Bid:
        match = BID_PATTERN.fullmatch(text)
        if match is None:
            raise NotationError(f"{text!r} is not a bid like 'bid 3'")
        return Bid(int(match.group(1)))

    def describe_action(self, observation: Observation, action: Bid) -> str:
        lot = json_str(observation.data, "current_lot")
        if action.coins == 0:
            return f"Pass on {lot} (bid 0)"
        if observation.viewer is None:
            return f"Bid {action.coins} coins for {lot}"
        coins = json_list_of(observation.data, "coins", int)[observation.viewer]
        return f"Bid {action.coins} of your {coins} coins for {lot}"

    def action_json(self, action: Bid) -> dict[str, JsonValue]:
        return tagged_json_object(action)


def check_config(config: SealedAuctionConfig) -> None:
    """Raise ConfigError for an unplayable config."""
    if not 2 <= config.num_players <= 4:
        raise ConfigError(f"sealed auction needs 2-4 players, got {config.num_players}")
    deck_size = len(COLORS) * len(LOT_VALUES)
    if not 1 <= config.lots <= deck_size:
        raise ConfigError(f"lots must be between 1 and {deck_size}")
    if not 0 <= config.starting_coins <= MAX_COINS:
        raise ConfigError(f"starting_coins must be between 0 and {MAX_COINS}")
    return


def deal_colors(rng: Rng, count: int) -> tuple[tuple[Color, ...], Rng]:
    """One secret color per player, each chosen uniformly."""
    colors: list[Color] = []
    for _ in range(count):
        color, rng = rng.choice(COLORS)
        colors.append(color)
    return tuple(colors), rng


def color_events(secret_colors: tuple[Color, ...]) -> list[Event]:
    """A private event per player with their color, then a public notice."""
    private = [
        Event(
            "color_dealt",
            f"{seat_label(PlayerId(player))}'s secret color is {color}.",
            {"player": player, "color": color},
            audience=frozenset({PlayerId(player)}),
        )
        for player, color in enumerate(secret_colors)
    ]
    public = Event("colors_dealt", "Each player was dealt a secret color.")
    return [*private, public]


def lot_event(state: SealedAuctionState) -> Event:
    """Public event revealing the current lot."""
    lot = state.current
    if lot is None:
        raise ValueError("no lot is up for auction")
    return Event(
        "lot_revealed",
        f"Lot {state.round} of {state.config.lots}: {lot}.",
        {"round": state.round, "color": lot.color, "value": lot.value},
    )


def bid_notation(action: Bid) -> str:
    """Notation of a bid: "bid 3"."""
    return f"bid {action.coins}"


def explain_bid(state: SealedAuctionState, player: PlayerId, action: Bid) -> str:
    """Why this bid is illegal for `player` now."""
    if state.current is None:
        return "The game is over."
    if state.bids[player] is not None:
        return "You already bid this round."
    if action.coins < 0:
        return "A bid cannot be negative."
    if action.coins > state.coins[player]:
        return (
            f"You have {state.coins[player]} coins, so you cannot bid {action.coins}."
        )
    return f"{bid_notation(action)!r} is not a legal bid now."


def check_bid(state: SealedAuctionState, player: PlayerId, action: Bid) -> None:
    """Raise IllegalActionError unless `player` may make this bid now."""
    if not 0 <= player < state.config.num_players:
        raise IllegalActionError(f"there is no seat {player}")
    if (
        state.current is None
        or state.bids[player] is not None
        or not 0 <= action.coins <= state.coins[player]
    ):
        raise IllegalActionError(explain_bid(state, player, action))
    return


def resolve_round(state: SealedAuctionState) -> Transition[SealedAuctionState]:
    """Reveal all bids, sell the lot, then reveal the next lot or end the game."""
    lot = state.current
    bids = tuple(bid for bid in state.bids if bid is not None)
    if lot is None or len(bids) != len(state.bids):
        raise ValueError("a round resolves only with a lot up and every bid in")
    top = max(bids)
    tied = [PlayerId(player) for player, bid in enumerate(bids) if bid == top]
    winner, rng = state.rng.choice(tied)
    events = tie_events(tied, top, winner)
    bid_text = ", ".join(
        f"{seat_label(PlayerId(player))} {bid}" for player, bid in enumerate(bids)
    )
    events.append(
        Event(
            "lot_sold",
            f"Bids: {bid_text}. {seat_label(winner)} wins {lot} for {top} coins.",
            {"bids": list(bids), "winner": winner, "price": top},
        )
    )
    coins = list(state.coins)
    coins[winner] -= top
    won = list(state.won)
    won[winner] = (*won[winner], lot)
    next_state = replace(
        state,
        rng=rng,
        deck=state.deck[1:],
        current=state.deck[0] if state.deck else None,
        round=state.round + 1 if state.deck else state.round,
        coins=tuple(coins),
        won=tuple(won),
        bids=(None,) * state.config.num_players,
    )
    if next_state.current is None:
        events.append(reveal_event(next_state))
    else:
        events.append(lot_event(next_state))
    return Transition(next_state, tuple(events))


def tie_events(tied: list[PlayerId], top: int, winner: PlayerId) -> list[Event]:
    """A public event naming the die-roll winner when several bids tie for top."""
    if len(tied) == 1:
        return []
    names = ", ".join(seat_label(player) for player in tied)
    return [
        Event(
            "tie_broken",
            f"{names} tied at {top}; a die roll picks {seat_label(winner)}.",
            {"tied": list(tied), "winner": winner},
        )
    ]


def reveal_event(state: SealedAuctionState) -> Event:
    """Public event revealing every secret color at the end."""
    text = ", ".join(
        f"{seat_label(PlayerId(player))} {color}"
        for player, color in enumerate(state.secret_colors)
    )
    return Event(
        "colors_revealed",
        f"Game over. Secret colors: {text}.",
        {"colors": list(state.secret_colors)},
    )


def score_breakdown(state: SealedAuctionState, player: PlayerId) -> dict[str, float]:
    """Points by source: lot values, secret color bonus, leftover coins."""
    lots = state.won[player]
    color = state.secret_colors[player]
    return {
        "lots": float(sum(lot.value for lot in lots)),
        "color bonus": float(sum(lot.value for lot in lots if lot.color == color)),
        "coins": float(state.coins[player] // 2),
    }


def round_line(data: JsonObject) -> str:
    """Which lot is up, or that the game is over."""
    total = json_int(data, "total_rounds")
    if data["current_lot"] is None:
        return f"Sealed auction: all {total} lots are sold; the game is over."
    lot = json_str(data, "current_lot")
    return f"Sealed auction, lot {json_int(data, 'round')} of {total}: {lot} is up."


def viewer_lines(viewer: PlayerId | None, data: JsonObject) -> list[str]:
    """The viewer's seat, secret color and sealed bid."""
    if viewer is None:
        return []
    lines = [
        f"You are {seat_label(viewer)}. Your secret color is "
        f"{json_str(data, 'your_color')}: lots of that color score double."
    ]
    bid = json_optional_int(data, "your_bid")
    if bid is not None:
        lines.append(f"Your sealed bid this round: {bid}.")
    return lines


def per_player(texts: list[str]) -> str:
    """ "P1 a; P2 b" from one text per seat."""
    return "; ".join(
        f"{seat_label(PlayerId(player))} {text}" for player, text in enumerate(texts)
    )


def bid_status(data: JsonObject) -> str:
    """Who has submitted a bid this round."""
    has_bid = json_list_of(data, "has_bid", bool)
    return per_player(["submitted" if done else "waiting" for done in has_bid])


def revealed_lines(data: JsonObject) -> list[str]:
    """Every player's secret color, once revealed at the end."""
    if data["revealed_colors"] is None:
        return []
    return [f"Secret colors: {per_player(json_str_list(data, 'revealed_colors'))}."]
