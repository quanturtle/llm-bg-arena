"""Exceptions raised by games and the engine."""


class ArenaError(Exception):
    """Base class for errors raised by Tabletop Arena."""


class IllegalActionError(ArenaError):
    """An action was applied that is not legal in the current state."""


class NotationError(ArenaError):
    """Text does not parse as an action, or two actions share one notation."""


class ConfigError(ArenaError):
    """A game or agent configuration is invalid."""


class UnknownGameError(ArenaError):
    """No game is registered under the requested id."""


class DuplicateGameError(ArenaError):
    """Two game classes were registered under the same id."""
