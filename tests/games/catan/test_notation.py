import pytest

from boardgames.core import IllegalActionError, NotationError
from boardgames.games.catan import (
    AcceptOffer,
    Action,
    BankTrade,
    BuildCity,
    BuyDev,
    DeclineOffer,
    Discard,
    EndTurn,
    MoveRobber,
    OfferTrade,
    PlaceRoad,
    PlaceSettlement,
    PlayKnight,
    PlayMonopoly,
    PlayRoadBuilding,
    PlayYearOfPlenty,
    Roll,
)
from tests.games.catan.support import GAME, P1, P2, action_state, play_setup


def test_notation_round_trips_every_action() -> None:
    actions: list[Action] = [
        Roll(),
        EndTurn(),
        PlaceSettlement(3),
        PlaceRoad(4),
        BuildCity(3),
        BuyDev(),
        Discard("wood"),
        MoveRobber(5, P2),
        MoveRobber(5, None),
        BankTrade("wood", 4, "ore"),
        OfferTrade("wood", "ore", P2),
        AcceptOffer(),
        DeclineOffer(),
        PlayKnight(5, P2),
        PlayRoadBuilding(),
        PlayYearOfPlenty("ore", "wood"),
        PlayMonopoly("wood"),
    ]
    for action in actions:
        assert GAME.parse_action(GAME.format_action(action)) == action


def test_year_of_plenty_keeps_both_resources_in_resource_order() -> None:
    reversed_pair = GAME.parse_action("play yearofplenty ore wood")
    assert isinstance(reversed_pair, PlayYearOfPlenty)
    assert (reversed_pair.first, reversed_pair.second) == ("wood", "ore")
    assert GAME.format_action(reversed_pair) == "play yearofplenty wood ore"
    for action in (PlayYearOfPlenty("ore", "wood"), PlayYearOfPlenty("wood", "ore")):
        assert GAME.parse_action(GAME.format_action(action)) == action
        assert action == reversed_pair


@pytest.mark.parametrize(
    "text",
    [
        "roll ",
        "end",
        "settle v01",
        "settle V1",
        "road e-1",
        "bank 0 wood for 1 ore",
        "bank 4 wood for 2 ore",
        "offer wood for wood to P0",
        "play knight h5 P0",
        "play yearofplenty wood",
        "discard",
        "robber h5 p2",
        "play road building",
    ],
)
def test_parse_rejects_non_canonical_text(text: str) -> None:
    with pytest.raises(NotationError):
        GAME.parse_action(text)


def test_off_board_ids_parse_but_are_illegal() -> None:
    action = GAME.parse_action("settle v999")
    state, _ = play_setup()
    with pytest.raises(IllegalActionError, match="not on the board"):
        GAME.apply(action_state(state), P1, action)
