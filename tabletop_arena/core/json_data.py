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


def json_int(data: JsonObject, key: str) -> int:
    """`data[key]` as an int; other types raise TypeError."""
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key!r} is {value!r}, expected an int")
    return value


def json_optional_int(data: JsonObject, key: str) -> int | None:
    """`data[key]` as an int or None; other types raise TypeError."""
    return None if data[key] is None else json_int(data, key)


def json_bool(data: JsonObject, key: str) -> bool:
    """`data[key]` as a bool; other types raise TypeError."""
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key!r} is {value!r}, expected a bool")
    return value


def json_str(data: JsonObject, key: str) -> str:
    """`data[key]` as a str; other types raise TypeError."""
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key!r} is {value!r}, expected a str")
    return value


def json_str_list(data: JsonObject, key: str) -> list[str]:
    """`data[key]` as a list of str; other types raise TypeError."""
    value = data[key]
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{key!r} is {value!r}, expected a list")
    items = list(value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{key!r} is {value!r}, expected strings")
    return [str(item) for item in items]


def json_object(data: JsonObject, key: str) -> JsonObject:
    """`data[key]` as a JSON object; other types raise TypeError."""
    value = data[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"{key!r} is {value!r}, expected an object")
    return value
