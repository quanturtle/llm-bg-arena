"""Terra Mystica: the standard base game for two to five players."""

from boardgames.games.terra_mystica.game import TerraMystica
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceDigging,
    AdvanceShipping,
    Board,
    BuildDwelling,
    Building,
    Hex,
    Pass,
    PowerAction,
    ReclaimPriest,
    SendPriest,
    TerraMysticaConfig,
    TerraMysticaState,
    TransformTerrain,
    UpgradeBuilding,
)

__all__ = [
    "Action",
    "AdvanceDigging",
    "AdvanceShipping",
    "Board",
    "BuildDwelling",
    "Building",
    "Hex",
    "Pass",
    "PowerAction",
    "ReclaimPriest",
    "SendPriest",
    "TerraMystica",
    "TerraMysticaConfig",
    "TerraMysticaState",
    "TransformTerrain",
    "UpgradeBuilding",
]
