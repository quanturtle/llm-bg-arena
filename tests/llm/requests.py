"""Decision requests built from real game states, for prompt and agent tests."""

from typing import Any

from boardgames.agents import DecisionRequest
from boardgames.core import AnyGame, Event, GameConfig
from boardgames.games.sealed_auction import Bid, SealedAuction, SealedAuctionConfig
from boardgames.games.tic_tac_toe import Mark, TicTacToe, TicTacToeConfig


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


def auction_request(coins: int = 10) -> DecisionRequest[Bid]:
    config = SealedAuctionConfig(num_players=3, lots=3, starting_coins=coins)
    return request_at(SealedAuction(), config, [])
