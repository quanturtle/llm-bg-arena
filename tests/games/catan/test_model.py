import pytest

from boardgames.games.catan.model import dev_with, empty_dev_hand, empty_hand, hand_with


def test_a_resource_cannot_be_removed_from_an_empty_hand() -> None:
    with pytest.raises(ValueError):
        hand_with(empty_hand(), "wood", -1)


def test_a_development_card_cannot_be_removed_from_an_empty_hand() -> None:
    with pytest.raises(ValueError):
        dev_with(empty_dev_hand(), "knight", -1)
