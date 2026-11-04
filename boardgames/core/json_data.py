"""JSON value types and the canonical encoding used for logs, hashes and caches."""

import hashlib
import json
from collections.abc import Mapping, Sequence

type JsonValue = (
    str | int | float | bool | Sequence[JsonValue] | Mapping[str, JsonValue] | None
)
type JsonObject = Mapping[str, JsonValue]


def clean_text(value: str) -> str:
    """Replace lone UTF-16 surrogates, which no UTF-8 file can hold."""
    return "".join(
        "\ufffd" if 0xD800 <= ord(character) <= 0xDFFF else character
        for character in value
    )


def clean_json(value: JsonValue) -> JsonValue:
    """`value` with lone surrogates in every string replaced."""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, Mapping):
        return {clean_text(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [clean_json(item) for item in value]
    return value


def canonical_json(value: JsonValue) -> str:
    """Encode with sorted keys and no whitespace, so equal values give equal text."""
    return json.dumps(
        clean_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


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


def json_list_of[T: str | int | bool](
    data: JsonObject, key: str, kind: type[T]
) -> list[T]:
    """`data[key]` as a list of `kind` items; other shapes raise TypeError."""
    return list_of(key, data[key], kind)


def json_str_list(data: JsonObject, key: str) -> list[str]:
    """`data[key]` as a list of str; other shapes raise TypeError."""
    return list_of(key, data[key], str)


def json_str_lists(data: JsonObject, key: str) -> list[list[str]]:
    """`data[key]` as a list of lists of str; other shapes raise TypeError."""
    return [list_of(key, item, str) for item in list_of_values(key, data[key])]


def list_of[T: str | int | bool](key: str, value: JsonValue, kind: type[T]) -> list[T]:
    """`value` as a list of `kind` items, where bools never count as ints."""
    items: list[T] = []
    for item in list_of_values(key, value):
        if not isinstance(item, kind) or (kind is int and isinstance(item, bool)):
            raise TypeError(f"{key!r} holds {item!r}, expected {kind.__name__}")
        items.append(item)
    return items


def list_of_values(key: str, value: JsonValue) -> Sequence[JsonValue]:
    """`value` as a sequence that is not a string."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{key!r} is {value!r}, expected a list")
    return value


def json_object(data: JsonObject, key: str) -> JsonObject:
    """`data[key]` as a JSON object; other types raise TypeError."""
    value = data[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"{key!r} is {value!r}, expected an object")
    return value
