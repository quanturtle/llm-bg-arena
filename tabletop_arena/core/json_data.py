"""JSON value types and the canonical encoding used for logs, hashes and caches."""

import hashlib
import json
from collections.abc import Mapping, Sequence

type JsonValue = (
    str | int | float | bool | Sequence[JsonValue] | Mapping[str, JsonValue] | None
)
type JsonObject = Mapping[str, JsonValue]


def canonical_json(value: JsonValue) -> str:
    """Encode with sorted keys and no whitespace, so equal values give equal text."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def json_digest(value: JsonValue) -> str:
    """Hex SHA-256 of the canonical encoding."""
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
