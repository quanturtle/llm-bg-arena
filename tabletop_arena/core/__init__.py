"""Core engine API: the Game protocol and the types it exchanges."""

from tabletop_arena.core.actions import ActionSpace, FlatActionSpace, Tokens
from tabletop_arena.core.decisions import Decision
from tabletop_arena.core.errors import (
    ArenaError,
    ConfigError,
    DuplicateGameError,
    IllegalActionError,
    NotationError,
    UnknownGameError,
)
from tabletop_arena.core.events import EVERYONE, Audience, Event, Everyone
from tabletop_arena.core.game import Game, GameConfig, Transition
from tabletop_arena.core.json_data import (
    JsonObject,
    JsonValue,
    canonical_json,
    json_digest,
)
from tabletop_arena.core.observation import Observation
from tabletop_arena.core.players import PlayerId, seat_label, seats
from tabletop_arena.core.registry import (
    AnyGame,
    create_game,
    register_game,
    registered_game_ids,
)
from tabletop_arena.core.rng import Rng
from tabletop_arena.core.scores import Scores

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
    "create_game",
    "json_digest",
    "register_game",
    "registered_game_ids",
    "seat_label",
    "seats",
]
