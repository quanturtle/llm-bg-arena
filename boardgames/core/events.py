"""Events: what `apply` reports, the backbone of logs, replays and recaps."""

from dataclasses import dataclass, field
from enum import Enum

from boardgames.core.json_data import JsonObject, JsonValue
from boardgames.core.players import PlayerId


class Everyone(Enum):
    """Audience of a public event."""

    EVERYONE = "everyone"


EVERYONE = Everyone.EVERYONE

type Audience = Everyone | frozenset[PlayerId]


@dataclass(frozen=True)
class Event:
    """Something that happened, as a one-line `text` and a machine-readable `data`.

    A private event (a card drawn into a hand) names its audience; spectators see none.
    """

    kind: str
    text: str
    data: JsonObject = field(default_factory=dict)
    audience: Audience = EVERYONE

    def is_visible_to(self, viewer: PlayerId | None) -> bool:
        """Whether `viewer` may see this event; viewer None is a spectator."""
        if isinstance(self.audience, Everyone):
            return True
        return viewer is not None and viewer in self.audience

    def to_json(self) -> dict[str, JsonValue]:
        """Machine form for logs."""
        audience: JsonValue = (
            self.audience.value
            if isinstance(self.audience, Everyone)
            else sorted(self.audience)
        )
        return {
            "kind": self.kind,
            "text": self.text,
            "data": self.data,
            "audience": audience,
        }
