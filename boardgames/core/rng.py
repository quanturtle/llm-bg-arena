"""Seeded, immutable random numbers that live inside game state.

Games store an `Rng` in their state and thread it through: every draw returns
the value and the next generator. The algorithm is SplitMix64, written out here
so results never change across Python versions.
"""

from collections.abc import Sequence
from dataclasses import dataclass

MASK_64 = (1 << 64) - 1
GOLDEN_GAMMA = 0x9E3779B97F4A7C15


@dataclass(frozen=True)
class Rng:
    """Immutable SplitMix64 generator; each draw returns `(value, next_rng)`."""

    state: int

    @classmethod
    def seeded(cls, seed: int) -> "Rng":
        """Generator for a match seed; any integer works."""
        return cls(seed & MASK_64)

    def next_u64(self) -> tuple[int, "Rng"]:
        """Uniform 64-bit unsigned integer."""
        state = (self.state + GOLDEN_GAMMA) & MASK_64
        mixed = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) & MASK_64
        mixed = ((mixed ^ (mixed >> 27)) * 0x94D049BB133111EB) & MASK_64
        return mixed ^ (mixed >> 31), Rng(state)

    def below(self, bound: int) -> tuple[int, "Rng"]:
        """Uniform integer in [0, bound), without modulo bias; `bound` is 1 to 2**64."""
        if not 1 <= bound <= 1 << 64:
            raise ValueError(f"bound must be from 1 to 2**64, got {bound}")
        accepted_below = (1 << 64) - (1 << 64) % bound
        value, rng = self.next_u64()
        while value >= accepted_below:
            value, rng = rng.next_u64()
        return value % bound, rng

    def roll(self, sides: int) -> tuple[int, "Rng"]:
        """Die roll from 1 to `sides`."""
        value, rng = self.below(sides)
        return value + 1, rng

    def choice[T](self, items: Sequence[T]) -> tuple[T, "Rng"]:
        """One item chosen uniformly."""
        index, rng = self.below(len(items))
        return items[index], rng

    def shuffled[T](self, items: Sequence[T]) -> tuple[tuple[T, ...], "Rng"]:
        """A uniformly shuffled copy, by Fisher-Yates."""
        result = list(items)
        rng = self
        for last in range(len(result) - 1, 0, -1):
            swap, rng = rng.below(last + 1)
            result[last], result[swap] = result[swap], result[last]
        return tuple(result), rng
