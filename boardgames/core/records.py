"""Conversion between flat dataclasses (configs, actions) and JSON objects."""

import dataclasses
import re
from enum import Enum
from typing import Literal, get_args, get_origin, get_type_hints

from boardgames.core.errors import ConfigError
from boardgames.core.json_data import JsonObject, JsonValue


def to_json_object(instance: object) -> dict[str, JsonValue]:
    """Fields of a dataclass instance as JSON; nested dataclasses and tuples recurse."""
    if not dataclasses.is_dataclass(instance) or isinstance(instance, type):
        raise TypeError(f"expected a dataclass instance, got {instance!r}")
    return {
        field.name: to_json_value(getattr(instance, field.name))
        for field in dataclasses.fields(instance)
    }


def to_json_value(value: object) -> JsonValue:
    """One field value as JSON."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if isinstance(value, tuple | list | frozenset):
        return [to_json_value(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return to_json_object(value)
    raise TypeError(f"cannot encode {value!r} as JSON")


def tagged_json_object(instance: object) -> dict[str, JsonValue]:
    """Like `to_json_object`, plus a "type" key with the class name in snake_case."""
    tag = re.sub(r"(?<!^)(?=[A-Z])", "_", type(instance).__name__).lower()
    return {"type": tag, **to_json_object(instance)}


def dataclass_from_json[T](cls: type[T], raw: JsonObject) -> T:
    """Build a dataclass with str, int, float, bool or Literal fields from JSON.

    Unknown keys, missing required keys and wrong value types raise ConfigError.
    """
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")
    hints = get_type_hints(cls)
    names = {field.name for field in dataclasses.fields(cls)}
    unknown = sorted(set(raw) - names)
    if unknown:
        raise ConfigError(f"{cls.__name__}: unknown keys {unknown}")
    for name, value in raw.items():
        check_field_type(cls.__name__, name, hints[name], value)
    try:
        return cls(**raw)
    except TypeError as error:
        raise ConfigError(f"{cls.__name__}: {error}") from error


def check_field_type(owner: str, name: str, hint: object, value: JsonValue) -> None:
    """Raise ConfigError unless `value` fits the field's type hint."""
    if get_origin(hint) is Literal:
        is_valid = value in get_args(hint)
    elif hint is bool:
        is_valid = isinstance(value, bool)
    elif hint is int:
        is_valid = isinstance(value, int) and not isinstance(value, bool)
    elif hint is float:
        is_valid = isinstance(value, int | float) and not isinstance(value, bool)
    elif hint is str:
        is_valid = isinstance(value, str)
    else:
        raise TypeError(f"{owner}.{name}: unsupported field type {hint!r}")
    if not is_valid:
        raise ConfigError(f"{owner}.{name}: {value!r} does not match {hint!r}")
    return
