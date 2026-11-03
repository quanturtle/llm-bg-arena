import asyncio

from boardgames.agents import Agent, Chosen, DecisionRequest, RandomAgent
from boardgames.core import (
    ActionSpace,
    Decision,
    NotationError,
    Observation,
    PlayerId,
)
from boardgames.games.tic_tac_toe import Mark, TicTacToe, TicTacToeConfig
from tests.core.test_actions import Move, Pass, Step, StepSpace, step_notation

TIC_TAC_TOE_GAME = TicTacToe()


class StepText:
    def format_action(self, action: Step) -> str:
        return step_notation(action)

    def parse_action(self, text: str) -> Step:
        tokens = text.split(" ")
        if tokens == ["pass"]:
            return Pass()
        if len(tokens) == 3 and tokens[0] == "move" and tokens[2].isdigit():
            return Move(tokens[1], int(tokens[2]))
        raise NotationError(f"{text!r} is not a step")

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
    state = TIC_TAC_TOE_GAME.setup(TicTacToeConfig(), 0).state
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


def test_reaches_every_legal_cell() -> None:
    request = tic_tac_toe_request()
    cells = {choose(RandomAgent(seed=seed), request) for seed in range(40)}
    assert cells == {Mark(row, col) for row in range(3) for col in range(3)}
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
