from itertools import product

from hypothesis import given, settings
from hypothesis import strategies as st

from boardgames.core import PlayerId, seats
from boardgames.games.catan import Catan, CatanConfig, CatanState
from boardgames.games.catan.geometry import VERTEX_NEIGHBORS
from boardgames.games.catan.model import (
    DEV_DECK_COUNTS,
    LARGEST_ARMY_MINIMUM,
    LONGEST_ROAD_MINIMUM,
    MAX_CITIES,
    MAX_ROADS,
    MAX_SETTLEMENTS,
    building_counts,
    hand_total,
    road_count,
)
from boardgames.games.catan.rules import longest_road_lengths
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
from boardgames.games.tic_tac_toe import (
    TicTacToe,
    TicTacToeConfig,
    TicTacToeState,
)
from tests.invariants.playthrough import random_playthrough

SEEDS = st.integers(min_value=0, max_value=2**32 - 1)
TIC_TAC_TOE = TicTacToe()
AUCTION = SealedAuction()
CATAN = Catan()
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


def has_line(state: TicTacToeState) -> bool:
    """Brute force: one player owns three cells in a row, column or diagonal."""
    for row, col, (d_row, d_col) in product(range(3), range(3), DIRECTIONS):
        end_row, end_col = row + 2 * d_row, col + 2 * d_col
        if not (0 <= end_row < 3 and 0 <= end_col < 3):
            continue
        owners = {state.board[row + i * d_row][col + i * d_col] for i in range(3)}
        if len(owners) == 1 and None not in owners:
            return True
    return False


PUERTO_RICO = PuertoRico()


def check_tic_tac_toe(state: TicTacToeState) -> None:
    """Marks alternate, and the game ends at a line or a full board."""
    cells = [cell for row in state.board for cell in row]
    x_marks = cells.count(PlayerId(0))
    o_marks = cells.count(PlayerId(1))
    assert x_marks - o_marks in (0, 1)
    assert state.to_move == PlayerId(x_marks - o_marks)
    is_full = None not in cells
    assert TIC_TAC_TOE.is_terminal(state) == (has_line(state) or is_full)
    return


def check_auction(state: SealedAuctionState) -> None:
    """Coins only go to the bank as winning bids; every lot is accounted for."""
    config = state.config
    paid = config.starting_coins * config.num_players - sum(state.coins)
    out = [lot for lots in state.won for lot in lots] + list(state.unsold)
    assert all(coins >= 0 for coins in state.coins)
    assert paid >= 0
    assert len(out) + len(state.deck) + (state.current is not None) == config.lots
    assert len(set(out) | set(state.deck)) == len(out) + len(state.deck)
    for player in seats(config.num_players):
        bid = state.bids[player]
        assert bid is None or 0 <= bid <= state.coins[player]
    scores = AUCTION.scores(state)
    for player, points in scores.points.items():
        assert points == sum(scores.breakdown[player].values())
    return


def check_catan(state: CatanState) -> None:
    """Pieces respect limits and spacing, cards never go negative, awards qualify."""
    for vertex, building in enumerate(state.buildings):
        if building is not None:
            assert all(
                state.buildings[other] is None for other in VERTEX_NEIGHBORS[vertex]
            )
    for player in seats(state.config.num_players):
        settlements, cities = building_counts(state, player)
        assert settlements <= MAX_SETTLEMENTS and cities <= MAX_CITIES
        assert road_count(state, player) <= MAX_ROADS
        assert all(count >= 0 for count in state.hands[player])
        assert all(count >= 0 for count in state.dev_hands[player])
    dev_cards = sum(hand_total(hand) for hand in state.dev_hands)
    assert dev_cards + len(state.dev_deck) + sum(state.knights_played) <= len(
        DEV_DECK_COUNTS
    )
    lengths = longest_road_lengths(state)
    if state.longest_road is not None:
        assert lengths[state.longest_road] == max(lengths) >= LONGEST_ROAD_MINIMUM
    knights = state.knights_played
    if state.largest_army is not None:
        assert knights[state.largest_army] == max(knights) >= LARGEST_ARMY_MINIMUM
    assert (state.phase == "discard") == any(state.discard_remaining)
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
    colonists = (
        state.colonist_supply
        + state.colonist_ship
        + sum(
            player.colonists_unplaced
            + sum(1 for plantation in player.plantations if plantation.colonized)
            + player.occupied_quarries
            + sum(building.colonists for building in player.buildings)
            for player in state.players
        )
    )
    expected_colonists = (
        COLONIST_SUPPLY[state.config.num_players] + state.config.num_players
    )
    assert colonists == expected_colonists
    return


@settings(max_examples=2000, deadline=None)
@given(seed=SEEDS)
def test_tic_tac_toe_random_play_keeps_invariants(seed: int) -> None:
    config = TicTacToeConfig()
    state, steps = random_playthrough(TIC_TAC_TOE, config, seed, check_tic_tac_toe)
    assert 5 <= steps <= 9
    assert sum(TIC_TAC_TOE.scores(state).points.values()) == 1.0
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


@settings(max_examples=4, deadline=None)
@given(seed=SEEDS, players=st.integers(3, 4))
def test_catan_random_play_keeps_invariants(seed: int, players: int) -> None:
    config = CatanConfig(num_players=players, victory_points=3)
    state, _ = random_playthrough(CATAN, config, seed, check_catan)
    assert state.winner is not None
    assert CATAN.scores(state).points[state.winner] >= config.victory_points
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
