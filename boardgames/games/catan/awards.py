"""Catan awards and victory: longest road, largest army and the end of the game."""

from dataclasses import replace

from boardgames.core import Event, JsonValue, PlayerId, Transition, seat_label, seats
from boardgames.games.catan.model import (
    LARGEST_ARMY_MINIMUM,
    LONGEST_ROAD_MINIMUM,
    CatanState,
    point_breakdown,
    total_points,
)
from boardgames.games.catan.rules import longest_road_length, longest_road_lengths


def longest_road_holder(
    lengths: tuple[int, ...], current: PlayerId | None, *, is_broken: bool
) -> PlayerId | None:
    """The sole longest road of at least 5; an unbroken holder keeps a tie."""
    best = max(lengths)
    if best < LONGEST_ROAD_MINIMUM:
        return None
    leaders = [
        PlayerId(player) for player, length in enumerate(lengths) if length == best
    ]
    if current in leaders and not is_broken:
        return current
    return leaders[0] if len(leaders) == 1 else None


def update_longest_road(
    previous: CatanState, state: CatanState
) -> tuple[CatanState, list[Event]]:
    """Recompute the award, keeping an unbroken holder through a tie."""
    lengths = longest_road_lengths(state)
    best = max(lengths)
    current = state.longest_road
    is_broken = current is not None and lengths[current] < longest_road_length(
        previous, current
    )
    holder = longest_road_holder(lengths, current, is_broken=is_broken)
    if holder == current:
        return state, []
    events: list[Event] = []
    if current is not None:
        events.append(
            Event(
                "longest_road_lost",
                f"{seat_label(current)} lost the longest road.",
                {"player": current},
            )
        )
    if holder is not None:
        events.append(
            Event(
                "longest_road",
                f"{seat_label(holder)} has the longest road with {best} paths.",
                {"player": holder, "length": best},
            )
        )
    return replace(state, longest_road=holder), events


def update_largest_army(
    state: CatanState,
) -> tuple[CatanState, list[Event]]:
    """Recompute the largest army award after a knight is played."""
    counts = state.knights_played
    best = max(counts)
    current = state.largest_army
    if (
        current is not None
        and counts[current] >= LARGEST_ARMY_MINIMUM
        and counts[current] == best
    ):
        holder = current
    elif best >= LARGEST_ARMY_MINIMUM:
        holder = PlayerId(
            min(player for player, count in enumerate(counts) if count == best)
        )
    else:
        holder = None
    if holder == current:
        return state, []
    events: list[Event] = []
    if current is not None:
        events.append(
            Event(
                "largest_army_lost",
                f"{seat_label(current)} lost the largest army.",
                {"player": current},
            )
        )
    if holder is not None:
        events.append(
            Event(
                "largest_army",
                f"{seat_label(holder)} has the largest army with {best} knights.",
                {"player": holder, "knights": best},
            )
        )
    return replace(state, largest_army=holder), events


def finish_if_won(
    state: CatanState, events: tuple[Event, ...]
) -> Transition[CatanState]:
    """End the game as soon as any player reaches the victory-point target."""
    players = seats(state.config.num_players)
    points = {player: total_points(state, player) for player in players}
    best = max(points.values())
    if best < state.config.victory_points:
        return Transition(state, events)
    winners = [player for player in players if points[player] == best]
    winner = state.active if state.active in winners else winners[0]
    scores: list[JsonValue] = [
        {
            "player": player,
            "points": points[player],
            "breakdown": point_breakdown(state, player, include_hidden=True),
        }
        for player in players
    ]
    return Transition(
        replace(
            state,
            phase="game_over",
            winner=winner,
            pending_offer=None,
            free_roads=0,
        ),
        (
            *events,
            Event(
                "game_over",
                f"{seat_label(winner)} wins with {best:g} victory points.",
                {"winner": winner, "points": best, "scores": scores},
            ),
        ),
    )
