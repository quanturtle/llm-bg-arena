"""Decisions: a request for one player to choose an action, on or off their turn."""

from dataclasses import dataclass

from tabletop_arena.core.json_data import JsonValue
from tabletop_arena.core.players import PlayerId


@dataclass(frozen=True)
class Decision:
    """`kind` is game-defined ("move", "bid"); `prompt` says what is being asked."""

    player: PlayerId
    kind: str
    prompt: str

    def to_json(self) -> dict[str, JsonValue]:
        """Machine form for logs."""
        return {"player": self.player, "kind": self.kind, "prompt": self.prompt}
