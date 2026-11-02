"""Observations: the part of the state one viewer may see."""

from dataclasses import dataclass

from tabletop_arena.core.json_data import JsonObject, json_digest
from tabletop_arena.core.players import PlayerId


@dataclass(frozen=True)
class Observation:
    """What `viewer` sees, as JSON data; viewer None is a spectator with public view."""

    viewer: PlayerId | None
    data: JsonObject

    def digest(self) -> str:
        """Stable hash of the data, logged with every decision."""
        return json_digest(self.data)
