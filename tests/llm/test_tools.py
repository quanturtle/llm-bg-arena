import json
from typing import Any

from boardgames.llm.model import ToolCall
from boardgames.llm.parsing import Rejected, Resolved
from boardgames.llm.prompting import PromptSettings
from boardgames.llm.tools import (
    DecisionProgress,
    ToolBudget,
    ToolResult,
    after_text_reply,
    after_tool_calls,
    answer_tool_call,
    answer_tool_calls,
    game_tools,
)
from tests.llm.requests import auction_request, tic_tac_toe_request

SETTINGS = PromptSettings()
BUDGET = ToolBudget(max_tool_calls=4, max_illegal_retries=1)


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall("call_1", name, json.dumps(arguments) if arguments else "")


def answer(name: str, request: Any = None, **arguments: Any) -> ToolResult[Any]:
    request = tic_tac_toe_request([]) if request is None else request
    return answer_tool_call(call(name, **arguments), request, SETTINGS)


def test_game_tools_end_with_take_action_taking_submit_fields() -> None:
    tools = game_tools(SETTINGS)
    assert [tool.name for tool in tools] == [
        "get_state",
        "get_rules",
        "get_recent_events",
        "list_legal_actions",
        "check_action",
        "take_action",
    ]
    assert tools[-1].parameters["required"] == ["reasoning", "action", "memory"]
    return


def test_reading_tools_return_the_request_texts() -> None:
    request = tic_tac_toe_request([])
    assert answer("get_state", request).text == request.observation_text
    assert answer("get_rules", request).text == request.rules
    assert answer("get_recent_events", request).text == "Nothing new."
    return


def test_list_legal_actions_numbers_a_small_space() -> None:
    text = answer("list_legal_actions").text
    assert text.startswith("1. a3")
    assert "9. c1" in text
    return


def test_list_legal_actions_walks_tokens_of_a_large_space() -> None:
    request = auction_request(coins=100)
    assert answer("list_legal_actions", request).text == "First tokens: bid."
    text = answer("list_legal_actions", request, prefix="bid").text
    assert text.startswith("Tokens that can follow 'bid': 0, 1, 2,")
    assert text.endswith("and 61 more.")
    complete = answer("list_legal_actions", request, prefix="bid 3").text
    assert complete == "'bid 3' is a complete legal action."
    assert answer("list_legal_actions", request, prefix="fold").text == (
        "No legal action starts with 'fold'."
    )
    return


def test_check_action_explains_illegal_and_malformed_actions() -> None:
    request = tic_tac_toe_request(["b2"])
    assert answer("check_action", request, action="a1").text == "'a1' is legal."
    assert answer("check_action", request, action="b2").text.startswith("Not legal:")
    assert answer("check_action", request, action="??").text.startswith(
        "Not valid notation:"
    )
    return


def test_take_action_resolves_or_rejects_like_a_submit() -> None:
    request = tic_tac_toe_request(["b2"])
    taken = answer("take_action", request, reasoning="r", action="a1", memory="m")
    assert taken.text == "Accepted: a1"
    assert isinstance(taken.outcome, Resolved)
    assert taken.reply is not None and taken.reply.memory == "m"
    rejected = answer("take_action", request, reasoning="r", action="b2", memory="")
    assert rejected.text.startswith("Not accepted:")
    assert isinstance(rejected.outcome, Rejected)
    assert rejected.outcome.kind == "illegal"
    return


def test_unknown_tool_and_bad_arguments_return_error_text() -> None:
    assert answer("fly").text.startswith("Unknown tool 'fly'. The tools are:")
    bad = answer_tool_call(
        ToolCall("c", "get_state", "not json"), tic_tac_toe_request([]), SETTINGS
    )
    assert bad.text == "The tool arguments must be a JSON object."
    return


def test_progress_commits_on_a_resolved_take_action() -> None:
    request = tic_tac_toe_request([])
    results = [
        answer("get_state", request),
        answer("take_action", request, action="a1"),
    ]
    progress = after_tool_calls(DecisionProgress[Any](), results, BUDGET)
    assert (progress.phase, progress.calls_made) == ("committed", 2)
    assert progress.chosen is not None
    return


def test_progress_exhausts_on_rejections_calls_or_text_replies() -> None:
    request = tic_tac_toe_request(["b2"])
    rejected = answer("take_action", request, action="b2")
    progress = after_tool_calls(DecisionProgress[Any](), [rejected], BUDGET)
    assert (progress.phase, progress.rejections) == ("exploring", 1)
    assert after_tool_calls(progress, [rejected], BUDGET).phase == "exhausted"
    lookups = [answer("get_rules", request)] * BUDGET.max_tool_calls
    assert after_tool_calls(DecisionProgress[Any](), lookups, BUDGET).phase == (
        "exhausted"
    )
    nudged = after_text_reply(DecisionProgress[Any](), BUDGET)
    assert (nudged.phase, nudged.text_replies) == ("exploring", 1)
    assert after_text_reply(nudged, BUDGET).phase == "exhausted"
    return


def test_an_accepted_action_commits_even_past_the_call_budget() -> None:
    request = tic_tac_toe_request([])
    results = [answer("get_rules", request)] * BUDGET.max_tool_calls
    results.append(answer("take_action", request, action="a1"))
    assert after_tool_calls(DecisionProgress[Any](), results, BUDGET).phase == (
        "committed"
    )
    return


def test_a_second_take_action_in_one_reply_is_ignored() -> None:
    request = tic_tac_toe_request([])
    calls = [call("take_action", action="a1"), call("take_action", action="b2")]
    results = answer_tool_calls(calls, request, SETTINGS)
    assert results[1].text.startswith("Ignored:")
    assert results[1].outcome is None
    return
