"""State builders and play helpers shared by the Puerto Rico tests."""

from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.puerto_rico import (
    PuertoRico,
    PuertoRicoConfig,
    PuertoRicoState,
    SelectRole,
)
from boardgames.games.puerto_rico.constants import Role
from boardgames.games.puerto_rico.model import (
    OwnedBuilding,
    Plantation,
    RoleState,
    goods_from,
    replace_player,
    replace_role,
    role_state,
)

GAME = PuertoRico()


def start(num_players: int = 3, seed: int = 7, **config: int) -> PuertoRicoState:
    return GAME.setup(PuertoRicoConfig(num_players=num_players, **config), seed).state


def notations(state: PuertoRicoState) -> list[str]:
    (decision,) = GAME.pending_decisions(state)
    listing = GAME.legal_actions(state, decision).listing(10_000)
    assert listing is not None
    return [GAME.format_action(action) for action in listing]


def play(state: PuertoRicoState, notation: str) -> PuertoRicoState:
    (decision,) = GAME.pending_decisions(state)
    action = GAME.parse_action(notation)
    return GAME.apply(state, decision.player, action).state


def select_role(state: PuertoRicoState, role: Role) -> PuertoRicoState:
    (decision,) = GAME.pending_decisions(state)
    return GAME.apply(state, decision.player, SelectRole(role)).state


def drain(state: PuertoRicoState) -> PuertoRicoState:
    """Play the current phase to its end, passing or finishing when possible."""
    while state.phase not in ("role_selection", "game_over"):
        options = notations(state)
        if "pass" in options:
            choice = "pass"
        elif "finish" in options:
            choice = "finish"
        elif "discard none" in options:
            choice = "discard none"
        else:
            choice = options[0]
        state = play(state, choice)
    return state


def with_doubloons(
    state: PuertoRicoState, player: PlayerId, amount: int
) -> PuertoRicoState:
    return replace_player(
        state, player, replace(state.players[player], doubloons=amount)
    )


def with_goods(
    state: PuertoRicoState, player: PlayerId, **counts: int
) -> PuertoRicoState:
    return replace_player(
        state, player, replace(state.players[player], goods=goods_from(**counts))
    )


def with_vp_chips(
    state: PuertoRicoState, player: PlayerId, amount: int
) -> PuertoRicoState:
    return replace_player(
        state, player, replace(state.players[player], vp_chips=amount)
    )


def with_buildings(
    state: PuertoRicoState,
    player: PlayerId,
    *buildings: OwnedBuilding,
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(state.players[player], buildings=buildings),
    )


def with_plantations(
    state: PuertoRicoState,
    player: PlayerId,
    *plantations: Plantation,
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(state.players[player], plantations=plantations),
    )


def with_quarries(
    state: PuertoRicoState,
    player: PlayerId,
    quarries: int,
    occupied: int = 0,
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(
            state.players[player],
            quarries=quarries,
            occupied_quarries=occupied,
        ),
    )


def with_colonists(
    state: PuertoRicoState, player: PlayerId, amount: int
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(state.players[player], colonists_unplaced=amount),
    )


def with_role(state: PuertoRicoState, role: Role, player: PlayerId) -> PuertoRicoState:
    entry = role_state(state, role)
    return replace_role(
        state, role, RoleState(role=role, doubloons=entry.doubloons, taken_by=player)
    )
