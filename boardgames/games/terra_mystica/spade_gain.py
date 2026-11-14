"""Award the Alchemists' power when they receive spades."""

from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.terra_mystica.constants import BuildingType, FactionType
from boardgames.games.terra_mystica.model import (
    TerraMysticaState,
    gain_power,
    replace_player,
)


def gain_spade_power(
    state: TerraMysticaState, player: PlayerId, spades: int
) -> TerraMysticaState:
    """Alchemists with a stronghold gain 2 power for each spade they receive."""
    owner = state.players[player]
    if (
        owner.profile.type is FactionType.ALCHEMISTS
        and state.board.count(player, BuildingType.STRONGHOLD) > 0
        and spades > 0
    ):
        owner = replace(owner, resources=gain_power(owner.resources, 2 * spades))
        state = replace_player(state, player, owner)
    return state
