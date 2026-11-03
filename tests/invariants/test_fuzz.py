from hypothesis import given, settings
from hypothesis import strategies as st

from boardgames.core import PlayerId, seats
from boardgames.games.k_in_a_row import (
    FOUR_IN_A_ROW,
    TIC_TAC_TOE,
    KInARow,
    KInARowConfig,
    KInARowState,
)
from boardgames.games.puerto_rico import (
    PuertoRico,
    PuertoRicoConfig,
    PuertoRicoState,
)
from boardgames.games.puerto_rico.constants import COLONIST_SUPPLY, GOOD_SUPPLY
from boardgames.games.puerto_rico.model import goods_total
from boardgames.games.sealed_auction import (
    SealedAuction,
    SealedAuctionConfig,
    SealedAuctionState,
)
from tests.invariants.playthrough import random_playthrough

SEEDS = st.integers(min_value=0, max_value=2**32 - 1)
K_IN_A_ROW = KInARow()
AUCTION = SealedAuction()
PUERTO_RICO = PuertoRico()


def check_k_in_a_row(state: KInARowState) -> None:
    """Marks alternate, so X has as many marks as O or one more."""
    cells = [cell for row in state.board for cell in row]
    x_marks = cells.count(PlayerId(0))
    o_marks = cells.count(PlayerId(1))
    assert x_marks - o_marks in (0, 1)
    assert state.to_move == PlayerId(x_marks - o_marks)
    return


def check_auction(state: SealedAuctionState) -> None:
    """Coins only go to the bank as winning bids; every lot is accounted for."""
    config = state.config
    paid = config.starting_coins * config.num_players - sum(state.coins)
    won = [lot for lots in state.won for lot in lots]
    assert all(coins >= 0 for coins in state.coins)
    assert paid >= 0
    assert len(won) + len(state.deck) + (state.current is not None) == config.lots
    assert len(set(won) | set(state.deck)) == len(won) + len(state.deck)
    for player in seats(config.num_players):
        bid = state.bids[player]
        assert bid is None or 0 <= bid <= state.coins[player]
    scores = AUCTION.scores(state)
    for player, points in scores.points.items():
        assert points == sum(scores.breakdown[player].values())
    return


def check_puerto_rico(state: PuertoRicoState) -> None:
    """Goods and colonists are conserved; nothing count-like goes negative."""
    assert all(count >= 0 for count in state.goods_supply)
    for player in state.players:
        assert all(count >= 0 for count in player.goods)
        assert player.doubloons >= 0
        assert player.vp_chips >= 0
        assert player.occupied_quarries <= player.quarries
    goods = (
        sum(state.goods_supply)
        + sum(goods_total(player.goods) for player in state.players)
        + sum(ship.filled for ship in state.cargo_ships)
        + len(state.trading_house)
    )
    assert goods == sum(GOOD_SUPPLY)
    colonists = state.colonist_supply + state.colonist_ship + sum(
        player.colonists_unplaced
        + sum(1 for plantation in player.plantations if plantation.colonized)
        + player.occupied_quarries
        + sum(building.colonists for building in player.buildings)
        for player in state.players
    )
    expected_colonists = (
        COLONIST_SUPPLY[state.config.num_players] + state.config.num_players
    )
    assert colonists == expected_colonists
    return


@settings(max_examples=2000, deadline=None)
@given(seed=SEEDS)
def test_tic_tac_toe_random_play_keeps_invariants(seed: int) -> None:
    state, steps = random_playthrough(K_IN_A_ROW, TIC_TAC_TOE, seed, check_k_in_a_row)
    assert 5 <= steps <= 9
    assert sum(K_IN_A_ROW.scores(state).points.values()) == 1.0
    return


@settings(max_examples=300, deadline=None)
@given(seed=SEEDS)
def test_four_in_a_row_random_play_keeps_invariants(seed: int) -> None:
    _, steps = random_playthrough(K_IN_A_ROW, FOUR_IN_A_ROW, seed, check_k_in_a_row)
    assert 7 <= steps <= 42
    return


@settings(max_examples=100, deadline=None)
@given(
    seed=SEEDS, rows=st.integers(1, 6), cols=st.integers(1, 6), gravity=st.booleans()
)
def test_any_board_size_terminates(
    seed: int, rows: int, cols: int, gravity: bool
) -> None:
    k = min(3, max(rows, cols))
    if k < 2:
        return
    config = KInARowConfig(rows=rows, cols=cols, k=k, gravity=gravity)
    random_playthrough(K_IN_A_ROW, config, seed, check_k_in_a_row)
    return


@settings(max_examples=1000, deadline=None)
@given(seed=SEEDS, players=st.integers(2, 4), lots=st.integers(1, 12))
def test_auction_random_play_keeps_invariants(
    seed: int, players: int, lots: int
) -> None:
    config = SealedAuctionConfig(num_players=players, lots=lots, starting_coins=8)
    _, steps = random_playthrough(AUCTION, config, seed, check_auction)
    assert steps == players * lots
    return


@settings(max_examples=20, deadline=None)
@given(
    seed=SEEDS,
    players=st.integers(3, 5),
    rounds=st.integers(1, 2),
)
def test_puerto_rico_random_play_keeps_invariants(
    seed: int, players: int, rounds: int
) -> None:
    config = PuertoRicoConfig(num_players=players, max_rounds=rounds)
    random_playthrough(PUERTO_RICO, config, seed, check_puerto_rico)
    return
