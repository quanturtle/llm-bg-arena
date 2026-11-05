"""Tests for Terra Mystica action notation."""

import pytest

from boardgames.core import NotationError
from boardgames.games.terra_mystica import (
    BuildDwelling,
    ChooseStrongholdPriests,
    Hex,
    PowerAction,
    TakeTownTile,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
)
from boardgames.games.terra_mystica.constants import BuildingType, Terrain
from tests.games.terra_mystica.support import GAME, listing, notations, play, start


def test_notation_round_trips_for_every_legal_action() -> None:
    state = start(num_players=2, seed=1)
    while not GAME.is_terminal(state):
        for action in listing(state):
            text = GAME.format_action(action)
            assert GAME.parse_action(text) == action
        state = play(state, notations(state)[0])


def test_river_notation_round_trips() -> None:
    river = Hex(1, 1)
    build = BuildDwelling(Hex(0, 0), river=river)
    assert GAME.format_action(build) == "build 0,0 river 1,1"
    assert GAME.parse_action("build 0,0 river 1,1") == build
    upgrade = UpgradeBuilding(Hex(1, 0), BuildingType.TEMPLE, river=river)
    assert GAME.format_action(upgrade) == "upgrade 1,0 temple river 1,1"
    assert GAME.parse_action("upgrade 1,0 temple river 1,1") == upgrade


def test_new_action_notation_round_trips() -> None:
    actions = (
        TakeTownTile(0),
        TradeVpForCoin(),
        TradeCoinsForVp(),
        ChooseStrongholdPriests(2),
        TransformTerrain(Hex(0, 0), Terrain.LAKE),
        UseCultSpade(Hex(0, 0), Terrain.LAKE),
        PowerAction("spade"),
        PowerAction("double_spade"),
    )
    for action in actions:
        assert GAME.parse_action(GAME.format_action(action)) == action


def test_parse_rejects_bad_notation() -> None:
    for text in ("", "build", "build x,y", "upgrade 0,0 castle", "priest sun 0"):
        with pytest.raises(NotationError):
            GAME.parse_action(text)
