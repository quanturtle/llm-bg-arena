"""Core engine API: the Game protocol and the types it exchanges."""

from boardgames.core.actions import ActionSpace, FlatActionSpace, Tokens
from boardgames.core.decisions import Decision
from boardgames.core.errors import (
    ArenaError,
    ConfigError,
    DuplicateGameError,
    IllegalActionError,
    NotationError,
    UnknownGameError,
)
from boardgames.core.events import EVERYONE, Audience, Event, Everyone
from boardgames.core.game import Game, GameConfig, Transition, checked_apply
from boardgames.core.json_data import (
    JsonObject,
    JsonValue,
    canonical_json,
    clean_json,
    clean_text,
    json_digest,
)
from boardgames.core.observation import Observation
from boardgames.core.players import PlayerId, seat_label, seats
from boardgames.core.registry import (
    AnyGame,
    create_game,
    register_game,
    registered_game_ids,
)
from boardgames.core.rng import Rng
from boardgames.core.scores import Scores

__all__ = [
    "EVERYONE",
    "ActionSpace",
    "AnyGame",
    "ArenaError",
    "Audience",
    "ConfigError",
    "Decision",
    "DuplicateGameError",
    "Event",
    "Everyone",
    "FlatActionSpace",
    "Game",
    "GameConfig",
    "IllegalActionError",
    "JsonObject",
    "JsonValue",
    "NotationError",
    "Observation",
    "PlayerId",
    "Rng",
    "Scores",
    "Tokens",
    "Transition",
    "UnknownGameError",
    "canonical_json",
    "checked_apply",
    "clean_json",
    "clean_text",
    "create_game",
    "json_digest",
    "register_game",
    "registered_game_ids",
    "seat_label",
    "seats",
]
