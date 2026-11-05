"""Final scoring for Terra Mystica: cults, area and leftover resources."""

from boardgames.core import PlayerId, seats
from boardgames.games.terra_mystica.constants import (
    AREA_FINAL_POINTS,
    CULT_FINAL_POINTS,
)
from boardgames.games.terra_mystica.model import (
    Board,
    TerraMysticaState,
    effective_reach,
)


def final_scores(
    state: TerraMysticaState,
) -> dict[PlayerId, tuple[int, dict[str, float]]]:
    """Final points: current VP, cult tracks, area and leftover resources."""
    all_seats = seats(len(state.players))
    base = {seat: state.players[seat].victory_points for seat in all_seats}
    cult = {seat: 0 for seat in all_seats}
    for cult_index in range(4):
        entries = [(seat, state.players[seat].cults[cult_index]) for seat in all_seats]
        awards = split_rank_points(entries, CULT_FINAL_POINTS)
        for seat, points in awards.items():
            cult[seat] += points
    sizes = {
        seat: largest_area(
            state.board,
            seat,
            state.players[seat].shipping,
            effective_reach(state.board, seat, state.players[seat].profile),
        )
        for seat in all_seats
    }
    area = {seat: 0 for seat in all_seats}
    awards = split_rank_points(
        [(seat, size) for seat, size in sizes.items()], AREA_FINAL_POINTS
    )
    for seat, points in awards.items():
        area[seat] += points
    resources = {
        seat: (
            state.players[seat].resources.coins
            + state.players[seat].resources.workers
            + state.players[seat].resources.priests
            + state.players[seat].resources.power3
            + state.players[seat].resources.power2 // 2
        )
        // state.players[seat].profile.final_coin_divisor
        for seat in all_seats
    }
    return {
        seat: (
            base[seat] + cult[seat] + area[seat] + resources[seat],
            {
                "base": base[seat],
                "cult": cult[seat],
                "area": area[seat],
                "resources": resources[seat],
            },
        )
        for seat in all_seats
    }


def split_rank_points(
    entries: list[tuple[PlayerId, int]], tiers: tuple[int, ...]
) -> dict[PlayerId, int]:
    """Split each tier's points evenly among tied players, rounding down."""
    awards = {seat: 0 for seat, _ in entries}
    positions = sorted({value for _, value in entries if value > 0}, reverse=True)
    place = 1
    for value in positions:
        group = [seat for seat, position in entries if position == value]
        count = len(group)
        tier_values = tiers[place - 1 : place - 1 + count]
        award = sum(tier_values) // count if count else 0
        for seat in group:
            awards[seat] += award
        place += count
        if place > len(tiers):
            break
    return awards


def largest_area(board: Board, player: PlayerId, shipping: int, reach: int = 0) -> int:
    """The size of the player's largest connected area."""
    largest = 0
    for position in board.occupied(player):
        largest = max(
            largest, len(board.connected_area(position, player, shipping, reach))
        )
    return largest
