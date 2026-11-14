"""Saved model configs: one named player per YAML file in a directory.

A config's name is its file stem. A saved config is never overwritten, so one
name always stands for one set of settings on the leaderboard.
"""

from pathlib import Path
from typing import Protocol

import yaml
from pydantic import TypeAdapter, ValidationError

from boardgames.arena.match_config import (
    ModelConfig,
    ModelConfigName,
    parse_model_config,
    read_yaml,
)
from boardgames.core import ArenaError, ConfigError

NAME: TypeAdapter[str] = TypeAdapter(ModelConfigName)


class UnknownModelConfigError(ArenaError):
    """No model config is saved under this name."""


class ModelConfigExistsError(ArenaError):
    """A model config is already saved under this name."""


class ModelConfigs(Protocol):
    def names(self) -> list[str]:
        """The saved config names, in order."""
        ...

    def get(self, name: str) -> ModelConfig:
        """The config saved as `name`; UnknownModelConfigError when there is none."""
        ...

    def save(self, name: str, config: ModelConfig) -> None:
        """Save a new config; ModelConfigExistsError when the name is taken."""
        ...

    def delete(self, name: str) -> None:
        """Remove a config; UnknownModelConfigError when there is none."""
        ...


def checked_name(name: str) -> str:
    """`name` when it is a valid config name, else ConfigError."""
    try:
        return NAME.validate_python(name)
    except ValidationError as error:
        raise ConfigError(
            f"{name!r} is not a model config name: use lowercase letters, digits, "
            "'.', '_' and '-', starting with a letter or digit"
        ) from error


class DirectoryModelConfigs:
    """One `<name>.yaml` per config under `root`; the directory may be missing."""

    def __init__(self, root: Path) -> None:
        self._root = root
        return

    def names(self) -> list[str]:
        """Stems of the directory's YAML files that are valid config names."""
        stems = sorted(path.stem for path in self._root.glob("*.yaml"))
        return [stem for stem in stems if NAME.validator.isinstance_python(stem)]

    def get(self, name: str) -> ModelConfig:
        path = self._path(name)
        if not path.is_file():
            raise UnknownModelConfigError(f"no model config named {name!r} in {path}")
        return parse_model_config(read_yaml(path), str(path))

    def save(self, name: str, config: ModelConfig) -> None:
        """Create the file; a retry after a successful save raises like a taken name."""
        path = self._path(name)
        text = yaml.safe_dump(
            config.model_dump(mode="json", exclude_none=True), sort_keys=False
        )
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as file:
                file.write(text)
        except FileExistsError as error:
            raise ModelConfigExistsError(
                f"a model config named {name!r} already exists; pick another name"
            ) from error
        return

    def delete(self, name: str) -> None:
        path = self._path(name)
        try:
            path.unlink()
        except FileNotFoundError as error:
            raise UnknownModelConfigError(
                f"no model config named {name!r} in {path}"
            ) from error
        return

    def _path(self, name: str) -> Path:
        return self._root / f"{checked_name(name)}.yaml"
