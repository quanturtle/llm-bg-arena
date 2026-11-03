"""Decision requests built from real game states, for prompt and agent tests."""

from typing import Any

from boardgames.agents import DecisionRequest
from boardgames.core import AnyGame, Event, GameConfig
from boardgames.games import catan, puerto_rico
from boardgames.games.catan import Catan, CatanConfig
from boardgames.games.puerto_rico import PuertoRico, PuertoRicoConfig
from boardgames.games.tic_tac_toe import Mark, TicTacToe, TicTacToeConfig

# Puerto Rico moves to a mayor decision of `pick plantation 0`, `... 1` and `finish`
MAYOR_MOVES = [
    "role settler",
    "take corn",
    "take corn",
    "take sugar",
    "role mayor",
    "place plantation 0",
    "place plantation 1",
]


def request_at(
    game: AnyGame,
    config: GameConfig,
    moves: list[str],
    events: tuple[Event, ...] = (),
    seed: int = 0,
) -> DecisionRequest[Any]:
    """Request for the first open decision after playing `moves` in decision order."""
    state = game.setup(config, seed).state
    for notation in moves:
        decision = game.pending_decisions(state)[0]
        state = game.apply(state, decision.player, game.parse_action(notation)).state
    decision = game.pending_decisions(state)[0]
    observation = game.observe(state, decision.player)
    return DecisionRequest(
        game_id=game.id,
        decision=decision,
        observation=observation,
        observation_text=game.render_text(observation),
        actions=game.legal_actions(state, decision),
        recent_events=events,
        rules=game.rules_text(),
        action_text=game,
    )


def tic_tac_toe_request(
    moves: list[str], events: tuple[Event, ...] = ()
) -> DecisionRequest[Mark]:
    return request_at(TicTacToe(), TicTacToeConfig(), moves, events)


def catan_request() -> DecisionRequest[catan.Action]:
    """The first settlement of a three-player game: `settle v0` to `settle v53`."""
    return request_at(Catan(), CatanConfig(num_players=3), [])


def puerto_rico_request(moves: list[str]) -> DecisionRequest[puerto_rico.Action]:
    return request_at(PuertoRico(), PuertoRicoConfig(num_players=3), moves)
