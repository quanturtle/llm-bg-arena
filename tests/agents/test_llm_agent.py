import asyncio
import json
from typing import Any

import pytest

from tabletop_arena.agents import AgentChoice, Chosen, DecisionRequest, Forfeited
from tabletop_arena.agents.llm_agent import LlmAgent, LlmAgentSettings
from tabletop_arena.arena.runner import play_match
from tabletop_arena.games.k_in_a_row import TIC_TAC_TOE, KInARow, Mark
from tabletop_arena.games.sealed_auction import Bid
from tabletop_arena.llm.model import (
    Completion,
    ModelSettings,
    TransientModelError,
    Usage,
)
from tabletop_arena.llm.parsing import ActionExtractor
from tabletop_arena.llm.prompting import PromptSettings
from tabletop_arena.llm.retry import RetryingChatModel
from tabletop_arena.logs.replay import replay_match
from tabletop_arena.logs.schema import DecisionRecord
from tests.arena.support import FakeClock, MemorySink, ScriptedAgent
from tests.llm.fakes import QueuedChatModel, reply
from tests.llm.requests import auction_request, tic_tac_toe_request
from tests.llm.test_model_layer import RecordedSleep

MODEL = ModelSettings(model="test/model")


def answer(action: str, memory: str = "", reasoning: str = "because") -> Completion:
    arguments = {"reasoning": reasoning, "action": action, "memory": memory}
    return reply(tool_arguments=json.dumps(arguments))


def agent(
    outcomes: list[Completion | Exception], **settings: Any
) -> tuple[LlmAgent, QueuedChatModel]:
    model = QueuedChatModel(outcomes)
    return LlmAgent(model, LlmAgentSettings(model=MODEL, **settings), seed=1), model


def decide[A](llm: LlmAgent, request: DecisionRequest[A]) -> AgentChoice[A]:
    return asyncio.run(llm.decide(request))


def test_legal_answer_is_chosen_with_its_trace() -> None:
    llm, model = agent([answer("b2", memory="took center", reasoning="center")])
    choice = decide(llm, tic_tac_toe_request([]))
    assert isinstance(choice, Chosen)
    assert choice.action == Mark(1, 1)
    trace = choice.trace
    assert (trace.reasoning, trace.memory) == ("center", "took center")
    assert (trace.prompt_tokens, trace.completion_tokens) == (100, 20)
    assert trace.cost_usd == pytest.approx(0.001)
    assert trace.attempts[0]["resolved_by"] == "strict"
    assert model.calls[0].tool is not None
    return


def test_illegal_answer_is_retried_with_the_rule() -> None:
    llm, model = agent([answer("b2"), answer("c3")])
    choice = decide(llm, tic_tac_toe_request(["b2"]))
    assert isinstance(choice, Chosen)
    assert choice.action == Mark(2, 2)
    assert choice.trace.illegal_attempts == 1
    retry = model.calls[1].messages
    assert [m.role for m in retry] == ["system", "user", "assistant", "user"]
    assert "b2 is already taken by X." in retry[-1].content
    assert len(choice.trace.attempts[1]["messages"]) == 2  # type: ignore[arg-type]
    return


def test_bad_tool_arguments_are_retried() -> None:
    llm, _ = agent([reply(tool_arguments="{oops"), answer("a1")])
    choice = decide(llm, tic_tac_toe_request([]))
    assert isinstance(choice, Chosen)
    assert choice.trace.attempts[0]["rejection"] == {
        "kind": "format",
        "feedback": "The tool arguments were not valid JSON.",
    }
    return


def test_forfeit_after_the_last_retry() -> None:
    llm, model = agent([answer("z9")] * 3, max_illegal_retries=2, fallback="forfeit")
    choice = decide(llm, tic_tac_toe_request([]))
    assert isinstance(choice, Forfeited)
    assert choice.reason == "no legal action after 3 attempts"
    assert (choice.trace.illegal_attempts, choice.trace.fallback) == (3, "forfeit")
    assert len(model.calls) == 3
    return


def test_random_fallback_plays_a_legal_action() -> None:
    llm, _ = agent([answer("z9")] * 2, max_illegal_retries=1, fallback="random")
    request = tic_tac_toe_request(["b2"])
    choice = decide(llm, request)
    assert isinstance(choice, Chosen)
    assert request.actions.is_legal(choice.action)
    assert choice.trace.fallback == "random"
    return


def test_default_fallback_plays_the_decision_default() -> None:
    llm, _ = agent([answer("bid 99")], max_illegal_retries=0, fallback="default")
    choice = decide(llm, auction_request())
    assert isinstance(choice, Chosen)
    assert (choice.action, choice.trace.fallback) == (Bid(0), "default")
    return


def test_default_fallback_without_a_default_plays_randomly() -> None:
    llm, _ = agent([answer("z9")], max_illegal_retries=0, fallback="default")
    choice = decide(llm, tic_tac_toe_request([]))
    assert isinstance(choice, Chosen)
    assert choice.trace.fallback == "random"
    return


def test_notes_carry_over_and_are_capped() -> None:
    llm, model = agent(
        [answer("a1", memory="x" * 50), answer("c1")],
        prompt=PromptSettings(memory_limit=10),
    )
    decide(llm, tic_tac_toe_request([]))
    assert llm.memory == "x" * 10
    decide(llm, tic_tac_toe_request(["a1", "b2"]))
    assert "# Your notes\nxxxxxxxxxx\n" in model.calls[1].messages[1].content
    return


def test_extractor_rescues_an_unmatched_reply() -> None:
    model = QueuedChatModel([answer("the middle one"), reply(text="b2")])
    extractor = ActionExtractor(model, ModelSettings(model="cheap"))
    llm = LlmAgent(model, LlmAgentSettings(model=MODEL), seed=1, extractor=extractor)
    choice = decide(llm, tic_tac_toe_request([]))
    assert isinstance(choice, Chosen)
    assert choice.action == Mark(1, 1)
    assert choice.trace.attempts[0]["resolved_by"] == "extractor"
    assert choice.trace.prompt_tokens == 200
    return


def test_text_mode_reads_the_final_answer_line() -> None:
    text = "Corners are strong.\nMemory: corners\nFinal Answer: a1"
    llm, model = agent([reply(text=text)], prompt=PromptSettings(output_mode="text"))
    choice = decide(llm, tic_tac_toe_request([]))
    assert isinstance(choice, Chosen)
    assert choice.action == Mark(0, 0)
    assert (choice.trace.reasoning, llm.memory) == ("Corners are strong.", "corners")
    assert model.calls[0].tool is None
    return


def test_unknown_price_makes_the_decision_cost_unknown() -> None:
    priced = answer("z9")
    unpriced = Completion(
        answer("a1").text, answer("a1").tool_arguments, Usage(1, 1), None
    )
    llm, _ = agent([priced, unpriced])
    choice = decide(llm, tic_tac_toe_request([]))
    assert choice.trace.cost_usd is None
    return


def test_api_retries_are_counted_apart_from_rejections() -> None:
    inner = QueuedChatModel([TransientModelError("429"), answer("a1")])
    model = RetryingChatModel(inner, sleep=RecordedSleep())
    llm = LlmAgent(model, LlmAgentSettings(model=MODEL), seed=1)
    choice = decide(llm, tic_tac_toe_request([]))
    assert (choice.trace.api_retries, choice.trace.illegal_attempts) == (1, 0)
    return


def test_llm_match_is_logged_and_replays() -> None:
    model = QueuedChatModel([answer("a1"), answer("a2"), answer("b1"), answer("c1")])
    llm = LlmAgent(model, LlmAgentSettings(model=MODEL, label="fake-llm"), seed=1)
    opponent = ScriptedAgent(["a2", "b2"])
    sink = MemorySink()
    asyncio.run(
        play_match(
            KInARow(),
            TIC_TAC_TOE,
            4,
            [llm, opponent],
            match_id="m",
            sink=sink,
            clock=FakeClock(),
        )
    )
    decisions = [r for r in sink.records if isinstance(r, DecisionRecord)]
    llm_turns = [d for d in decisions if d.player == 0]
    assert [d.action for d in llm_turns] == ["a1", "b1", "c1"]
    assert llm_turns[1].trace.illegal_attempts == 1
    assert llm_turns[0].trace.attempts[0]["messages"]
    assert replay_match(sink.records).steps == 5
    return
