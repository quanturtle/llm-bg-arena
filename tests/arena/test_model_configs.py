from pathlib import Path

import pytest

from boardgames.arena.match_config import ModelConfig
from boardgames.arena.model_configs import (
    DirectoryModelConfigs,
    ModelConfigExistsError,
)
from boardgames.core import ConfigError

HAIKU_LOW = ModelConfig(model="anthropic/claude-haiku-5.5", reasoning_effort="low")


def test_saved_config_is_listed_and_read_back(tmp_path: Path) -> None:
    configs = DirectoryModelConfigs(tmp_path / "models")
    configs.save("haiku-low", HAIKU_LOW)
    assert configs.names() == ["haiku-low"]
    assert configs.get("haiku-low") == HAIKU_LOW
    return


def test_saved_config_is_not_overwritten(tmp_path: Path) -> None:
    configs = DirectoryModelConfigs(tmp_path)
    configs.save("haiku-low", HAIKU_LOW)
    with pytest.raises(ModelConfigExistsError):
        configs.save("haiku-low", ModelConfig(model="a/b"))
    return


def test_name_that_is_a_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not a model config name"):
        DirectoryModelConfigs(tmp_path).delete("../match")
    return
