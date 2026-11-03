from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from boardgames.core.rng import Rng


def test_matches_reference_splitmix64_output() -> None:
    first, rng = Rng.seeded(0).next_u64()
    second, _ = rng.next_u64()
    assert (first, second) == (0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4)
    return


def test_draws_do_not_change_the_generator() -> None:
    rng = Rng.seeded(7)
    assert rng.below(100)[0] == rng.below(100)[0]
    assert rng == Rng.seeded(7)
    return


@given(seed=st.integers(), bound=st.integers(min_value=1, max_value=10**12))
def test_below_stays_in_range(seed: int, bound: int) -> None:
    value, _ = Rng.seeded(seed).below(bound)
    assert 0 <= value < bound
    return


def test_below_rejects_non_positive_bound() -> None:
    with pytest.raises(ValueError, match="positive"):
        Rng.seeded(1).below(0)
    return


def test_rolls_cover_every_face_evenly() -> None:
    rng = Rng.seeded(42)
    counts: Counter[int] = Counter()
    for _ in range(6000):
        face, rng = rng.roll(6)
        counts[face] += 1
    assert sorted(counts) == [1, 2, 3, 4, 5, 6]
    assert all(850 < count < 1150 for count in counts.values())
    return


@given(seed=st.integers(), items=st.lists(st.integers(), max_size=30))
def test_shuffle_is_a_permutation(seed: int, items: list[int]) -> None:
    shuffled, _ = Rng.seeded(seed).shuffled(items)
    assert sorted(shuffled) == sorted(items)
    return


def test_same_seed_gives_same_shuffle() -> None:
    deck = tuple(range(52))
    assert Rng.seeded(9).shuffled(deck) == Rng.seeded(9).shuffled(deck)
    assert Rng.seeded(9).shuffled(deck)[0] != Rng.seeded(10).shuffled(deck)[0]
    return
