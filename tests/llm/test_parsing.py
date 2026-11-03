import asyncio

import pytest

from boardgames.games.puerto_rico import PickUpColonist
from boardgames.games.tic_tac_toe import Mark
from boardgames.llm.model import ModelSettings
from boardgames.llm.parsing import (
    ActionExtractor,
    ParsedReply,
    Rejected,
    Resolved,
    parse_reply,
    parse_text,
    resolve_answer,
)
from tests.agents.test_random_agent import UnlistableStepSpace, step_request
from tests.core.test_actions import Move
from tests.llm.fakes import QueuedChatModel, reply
from tests.llm.requests import MAYOR_MOVES, puerto_rico_request, tic_tac_toe_request


def test_tool_arguments_give_answer_reasoning_and_memory() -> None:
    parsed = parse_reply(
        reply(tool_arguments='{"reasoning": "center", "action": "b2", "memory": "m"}')
    )
    assert parsed == ParsedReply(answer="b2", reasoning="center", memory="m")
    return


@pytest.mark.parametrize(
    ("arguments", "feedback"),
    [
        ("{not json", "not valid JSON"),
        ('["b2"]', "must be a JSON object"),
        ('{"reasoning": "x"}', 'non-empty "action"'),
    ],
)
def test_bad_tool_arguments_are_format_errors(arguments: str, feedback: str) -> None:
    parsed = parse_reply(reply(tool_arguments=arguments))
    assert isinstance(parsed, Rejected)
    assert parsed.kind == "format"
    assert feedback in parsed.feedback
    return


def test_text_reply_uses_the_last_final_answer_line() -> None:
    text = "Final Answer: a1 is tempting.\nBut b2 is better.\nMemory: hold center\n"
    text += "**Final Answer:** `b2`."
    parsed = parse_reply(reply(text=text))
    assert parsed == ParsedReply(
        answer="b2",
        reasoning="Final Answer: a1 is tempting.\nBut b2 is better.",
        memory="hold center",
    )
    return


def test_short_bare_text_reply_is_the_answer() -> None:
    assert parse_reply(reply(text=" c3 \n")) == ParsedReply("c3", None, None)
    return


def test_long_text_without_final_answer_is_a_format_error() -> None:
    parsed = parse_reply(reply(text="I think the center matters.\nSo maybe b2."))
    assert isinstance(parsed, Rejected)
    assert "Final Answer: <action>" in parsed.feedback
    return


def resolve_mark(answer: str, moves: list[str]) -> Resolved[Mark] | Rejected:
    request = tic_tac_toe_request(moves)
    return resolve_answer(answer, request, request.actions.listing(60))


def test_exact_notation_resolves_strictly() -> None:
    assert resolve_mark("b2", []) == Resolved(Mark(1, 1), "strict")
    return


def test_legal_notation_for_an_illegal_move_gets_the_rule() -> None:
    assert resolve_mark("b2", ["b2"]) == Rejected(
        "illegal", "b2 is already taken by X."
    )
    return


@pytest.mark.parametrize(
    ("answer", "cell"),
    [
        ("B2", Mark(1, 1)),
        ("I'll take the center, b2", Mark(1, 1)),
        ("Place X on c3", Mark(2, 2)),
        ("3", Mark(2, 2)),
    ],
    ids=["case", "mentioned", "description", "list-number"],
)
def test_loose_answers_resolve_to_one_legal_cell(answer: str, cell: Mark) -> None:
    resolved = resolve_mark(answer, [])
    assert isinstance(resolved, Resolved)
    assert resolved.action == cell
    return


def test_number_means_the_action_whose_notation_uses_it() -> None:
    request = puerto_rico_request(MAYOR_MOVES)
    resolved = resolve_answer("1", request, request.actions.listing(60))
    assert resolved == Resolved(PickUpColonist("plantation", 1), "soft")
    return


@pytest.mark.parametrize("answer", ["a1 or b2", "the corner", "99"])
def test_unclear_answers_are_unmatched_with_an_example(answer: str) -> None:
    resolved = resolve_mark(answer, [])
    assert isinstance(resolved, Rejected)
    assert resolved.kind == "unmatched"
    assert "for example 'a3'" in resolved.feedback
    return


def test_large_spaces_accept_only_strict_notation() -> None:
    request = step_request(UnlistableStepSpace())
    assert resolve_answer("move a 1", request, None) == Resolved(Move("a", 1), "strict")
    loose = resolve_answer("MOVE A 1", request, None)
    assert isinstance(loose, Rejected)
    assert loose.kind == "unmatched"
    return


def test_extractor_maps_a_reply_to_a_listed_action() -> None:
    model = QueuedChatModel([reply(text="b2"), reply(text="NONE")])
    extractor = ActionExtractor(model, ModelSettings(model="cheap"))
    request = tic_tac_toe_request([])
    found = asyncio.run(extractor.extract("the middle one", request))
    assert found.action == Mark(1, 1)
    assert "Legal actions: a3, b3, c3" in model.calls[0].messages[0].content
    missing = asyncio.run(extractor.extract("no idea", request))
    assert missing.action is None
    assert missing.completion.usage.prompt_tokens == 100
    return


def test_non_ascii_digits_are_not_numbers() -> None:
    assert isinstance(resolve_answer("²", tic_tac_toe_request([]), None), Rejected)
    return


def test_numbers_are_not_indexes_when_the_notation_has_numeric_tokens() -> None:
    request = puerto_rico_request(MAYOR_MOVES)
    numbered = request.actions.listing(60)
    assert isinstance(resolve_answer("3", request, numbered), Rejected)
    return


def test_text_reply_takes_the_last_memory_line_and_decorated_answers() -> None:
    parsed = parse_text("Memory: old\nthink\nMemory: new\n**Final Answer**: b2")
    assert isinstance(parsed, ParsedReply)
    assert (parsed.answer, parsed.memory) == ("b2", "new")
    assert isinstance(parse_text("Final Answer:\nMemory: notes"), Rejected)
    return
