"""Tests for the Puerto Rico action notation."""

import pytest

from boardgames.core import IllegalActionError, NotationError
from boardgames.games.puerto_rico import (
    Action,
    Build,
    DiscardGoods,
    FinishPlacement,
    LoadShip,
    LoadWharf,
    Pass,
    PickUpColonist,
    PlaceColonist,
    ProducePrivilege,
    SelectRole,
    Sell,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
)
from tests.games.puerto_rico.support import GAME, select_role, start, with_colonists


def test_notation_round_trips_every_action() -> None:
    actions: list[Action] = [
        SelectRole("settler"),
        SelectRole("prospector"),
        TakePlantation("corn"),
        TakePlantation("corn", use_hospice=False),
        TakeQuarry(),
        TakeQuarry(use_hospice=False),
        UseHacienda(),
        Pass(),
        Build("small_indigo_plant"),
        Build("small_indigo_plant", use_university=False),
        ProducePrivilege("coffee"),
        Sell("tobacco"),
        LoadShip("indigo", 0),
        LoadShip("coffee", 2),
        LoadWharf("sugar"),
        PlaceColonist("plantation", 0),
        PlaceColonist("building", 2),
        PlaceColonist("quarry"),
        PickUpColonist("plantation", 1),
        PickUpColonist("building", 0),
        PickUpColonist("quarry"),
        FinishPlacement(),
        DiscardGoods(),
        DiscardGoods(("corn", "indigo")),
        DiscardGoods(("corn",), "indigo"),
    ]
    for action in actions:
        assert GAME.parse_action(GAME.format_action(action)) == action


@pytest.mark.parametrize(
    "text",
    [
        "role",
        "role alien",
        "take",
        "take mango",
        "build",
        "build castle",
        "privilege",
        "privilege mango",
        "sell",
        "sell mango",
        "ship corn 1",
        "ship corn s0",
        "ship corn s4",
        "wharf corn s1",
        "place plantation",
        "place building -1",
        "place quarry 0",
        "pick building x",
        "discard mango",
        "discard ",
        "discard  indigo",
        "discard\tindigo",
        "finish ",
    ],
)
def test_parse_rejects_non_canonical_text(text: str) -> None:
    with pytest.raises(NotationError):
        GAME.parse_action(text)


def test_discard_notation_is_canonical() -> None:
    for text in (
        "discard none",
        "discard corn none",
        "discard keep indigo",
        "discard corn keep indigo",
    ):
        assert GAME.format_action(GAME.parse_action(text)) == text
    for text in (
        "discard",
        "discard corn",
        "discard keep corn none",
        "discard none keep corn",
    ):
        with pytest.raises(NotationError):
            GAME.parse_action(text)


def test_off_board_indices_parse_but_are_illegal() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 1)
    action = GAME.parse_action("place plantation 999")
    assert GAME.format_action(action) == "place plantation 999"
    with pytest.raises(IllegalActionError):
        GAME.apply(state, player, action)
