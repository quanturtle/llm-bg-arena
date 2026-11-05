"""Tests for the Puerto Rico Trader and the Office."""

from dataclasses import replace

from boardgames.games.puerto_rico.model import OwnedBuilding
from tests.games.puerto_rico.support import (
    drain,
    notations,
    play,
    select_role,
    start,
    with_buildings,
    with_goods,
)


def test_trader_sells_a_good_and_keeps_the_house_unless_full() -> None:
    state = start(seed=10)
    chooser = state.order[0]
    state = with_goods(state, chooser, indigo=1, sugar=2)
    state = select_role(state, "trader")
    assert state.phase == "trader_action"
    before = state.players[chooser].doubloons
    assert "sell indigo" in notations(state)
    state = play(state, "sell indigo")
    assert state.players[chooser].doubloons == before + 2
    assert state.trading_house == ("indigo",)
    state = drain(state)
    assert state.phase == "role_selection"
    assert state.trading_house == ("indigo",)


def test_office_allows_selling_a_duplicate_good() -> None:
    state = start(seed=10)
    chooser = state.order[0]
    state = with_goods(state, chooser, indigo=1)
    state = select_role(state, "trader")
    state = replace(state, trading_house=("indigo",))
    assert "sell indigo" not in notations(state)
    state = with_buildings(state, chooser, OwnedBuilding("office", 1))
    assert "sell indigo" in notations(state)
