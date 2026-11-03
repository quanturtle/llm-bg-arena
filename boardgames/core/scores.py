"""Scores: points per player, the source of rankings and ratings."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from boardgames.core.json_data import JsonValue
from boardgames.core.players import PlayerId


@dataclass(frozen=True)
class Scores:
    """Points per player, with an optional breakdown by source (buildings, awards)."""

    points: Mapping[PlayerId, float]
    breakdown: Mapping[PlayerId, Mapping[str, float]] = field(default_factory=dict)

    def ranks(self) -> dict[PlayerId, int]:
        """Rank 1 is best; tied players share the better rank (1, 1, 3)."""
        return {
            player: 1 + sum(1 for other in self.points.values() if other > points)
            for player, points in self.points.items()
        }

    def ranks_after_forfeits(
        self, forfeited: Collection[PlayerId]
    ) -> dict[PlayerId, int]:
        """Ranks by points among finishers; forfeiters share the rank after them."""
        finishers = Scores(
            {p: points for p, points in self.points.items() if p not in forfeited}
        )
        ranks = finishers.ranks()
        last = len(finishers.points) + 1
        return {player: ranks.get(player, last) for player in sorted(self.points)}

    def to_json(self) -> list[JsonValue]:
        """One entry per player, in seat order."""
        ranks = self.ranks()
        return [
            {
                "player": player,
                "points": self.points[player],
                "rank": ranks[player],
                "breakdown": dict(self.breakdown.get(player, {})),
            }
            for player in sorted(self.points)
        ]
