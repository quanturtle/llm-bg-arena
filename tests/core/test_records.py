from dataclasses import dataclass
from typing import Literal

import pytest

from boardgames.core import ConfigError, canonical_json, json_digest
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)


@dataclass(frozen=True)
class BoardConfig:
    num_players: int
    size: int = 3
    speed: float = 1.0
    gravity: bool = False
    variant: Literal["short", "long"] = "short"


@dataclass(frozen=True)
class PlaceStone:
    cells: tuple[int, ...]


def test_config_round_trips_through_json() -> None:
    config = BoardConfig(num_players=2, size=5, speed=2, variant="long")
    assert dataclass_from_json(BoardConfig, to_json_object(config)) == config
    return


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"num_players": 2, "colour": "red"}, "unknown keys"),
        ({"num_players": "2"}, "does not match"),
        ({"num_players": True}, "does not match"),
        ({"num_players": 2, "variant": "medium"}, "does not match"),
        ({"size": 3}, "num_players"),
    ],
)
def test_invalid_config_raises(raw: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        dataclass_from_json(BoardConfig, raw)  # type: ignore[arg-type]
    return


def test_tagged_object_names_the_class_in_snake_case() -> None:
    assert tagged_json_object(PlaceStone((1, 2))) == {
        "type": "place_stone",
        "cells": [1, 2],
    }
    return


def test_canonical_json_ignores_key_order() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json(
        {"a": [1, 2], "b": 1}
    )
    assert json_digest({"b": 1, "a": 2}) == json_digest({"a": 2, "b": 1})
    return
