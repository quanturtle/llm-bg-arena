import asyncio

from tabletop_arena.agents import Agent, Chosen, DecisionRequest, RandomAgent
from tabletop_arena.core import ActionSpace, Decision, Observation, PlayerId
from tabletop_arena.games.k_in_a_row import TIC_TAC_TOE, KInARow, Mark
from tabletop_arena.games.sealed_auction import Bid, SealedAuction, SealedAuctionConfig
from tests.core.test_actions import Move, Pass, Step, StepSpace, step_notation

TIC_TAC_TOE_GAME = KInARow()


class StepText:
    def format_action(self, action: Step) -> str:
        return step_notation(action)

    def parse_action(self, text: str) -> Step:
        raise NotImplementedError

    def describe_action(self, observation: Observation, action: Step) -> str:
        return step_notation(action)


def step_request(space: ActionSpace[Step]) -> DecisionRequest[Step]:
    return DecisionRequest(
        game_id="steps",
        decision=Decision(PlayerId(0), "step", "Move or pass."),
        observation=Observation(PlayerId(0), {}),
        observation_text="",
        actions=space,
        recent_events=(),
        rules="",
        action_text=StepText(),
    )


def tic_tac_toe_request() -> DecisionRequest[Mark]:
    state = TIC_TAC_TOE_GAME.setup(TIC_TAC_TOE, 0).state
    (decision,) = TIC_TAC_TOE_GAME.pending_decisions(state)
    observation = TIC_TAC_TOE_GAME.observe(state, decision.player)
    return DecisionRequest(
        game_id=TIC_TAC_TOE_GAME.id,
        decision=decision,
        observation=observation,
        observation_text=TIC_TAC_TOE_GAME.render_text(observation),
        actions=TIC_TAC_TOE_GAME.legal_actions(state, decision),
        recent_events=(),
        rules=TIC_TAC_TOE_GAME.rules_text(),
        action_text=TIC_TAC_TOE_GAME,
    )


def choose[A](agent: RandomAgent, request: DecisionRequest[A]) -> A:
    choice = asyncio.run(agent.decide(request))
    assert isinstance(choice, Chosen)
    return choice.action


def test_chooses_legal_cells() -> None:
    request = tic_tac_toe_request()
    agent = RandomAgent(seed=3)
    for _ in range(50):
        assert request.actions.is_legal(choose(agent, request))
    return


def test_same_seed_gives_same_choices() -> None:
    request = tic_tac_toe_request()
    first, second = RandomAgent(seed=11), RandomAgent(seed=11)
    assert [choose(first, request) for _ in range(20)] == [
        choose(second, request) for _ in range(20)
    ]
    return


def test_chooses_legal_bids() -> None:
    game = SealedAuction()
    state = game.setup(SealedAuctionConfig(starting_coins=4), 0).state
    decision = game.pending_decisions(state)[0]
    observation = game.observe(state, decision.player)
    request = DecisionRequest(
        game.id,
        decision,
        observation,
        game.render_text(observation),
        game.legal_actions(state, decision),
        (),
        game.rules_text(),
        game,
    )
    bids = {choose(RandomAgent(seed=seed), request) for seed in range(40)}
    assert bids == {Bid(coins) for coins in range(5)}
    return


class UnlistableStepSpace(StepSpace):
    """StepSpace that refuses to list itself, forcing the token-by-token walk."""

    def listing(self, limit: int) -> tuple[Step, ...] | None:
        return None


def test_satisfies_the_agent_protocol() -> None:
    agent: Agent = RandomAgent(seed=1)
    assert agent.settings() == {"kind": "random", "seed": 1}
    return


def test_walks_large_spaces_token_by_token() -> None:
    request = step_request(UnlistableStepSpace())
    agent = RandomAgent(seed=5)
    chosen = [choose(agent, request) for _ in range(200)]
    assert all(request.actions.is_legal(action) for action in chosen)
    assert Pass() in chosen
    assert any(isinstance(action, Move) for action in chosen)
    return
