from dataclasses import replace

from boardgames.core import Event, FlatActionSpace
from boardgames.llm.model import Message
from boardgames.llm.prompting import (
    MAX_TEMPLATE_LINES,
    PromptSettings,
    action_templates,
    build_prompt,
    recent_events_text,
    retry_messages,
    submit_tool,
)
from tests.agents.test_random_agent import UnlistableStepSpace, step_request
from tests.llm.requests import auction_request, tic_tac_toe_request

SETTINGS = PromptSettings()


def test_system_message_has_seat_rules_and_tool_instructions() -> None:
    prompt = build_prompt(tic_tac_toe_request(["a1"]), "", SETTINGS)
    system = prompt.messages[0]
    assert system.role == "system"
    assert system.content.startswith("You are P2, a player in a game of k_in_a_row.")
    assert "# Rules\n# k-in-a-row" in system.content
    assert "calling the submit_action tool" in system.content
    return


def test_text_mode_asks_for_a_final_answer_line() -> None:
    settings = PromptSettings(output_mode="text", persona="You play aggressively.")
    system = build_prompt(tic_tac_toe_request([]), "", settings).messages[0].content
    assert "You play aggressively." in system
    assert "Final Answer: <action>" in system
    return


def test_user_message_sections_in_order() -> None:
    events = (Event("marked", "P1 (X) marked a1."),)
    prompt = build_prompt(
        tic_tac_toe_request(["a1"], events), "Take the center.", SETTINGS
    )
    user = prompt.messages[1].content
    headers = [line for line in user.splitlines() if line.startswith("# ")]
    assert headers == [
        "# State",
        "# Since your last decision",
        "# Your notes",
        "# Decision",
        "# Legal actions",
    ]
    assert "- P1 (X) marked a1." in user
    assert "# Your notes\nTake the center." in user
    return


def test_few_actions_are_numbered_with_descriptions() -> None:
    prompt = build_prompt(tic_tac_toe_request(["a1"]), "", SETTINGS)
    user = prompt.messages[1].content
    assert "1. a3 — Place O on a3" in user
    assert "8. c1 — Place O on c1" in user
    assert prompt.numbered is not None and len(prompt.numbered) == 8
    return


def test_many_actions_switch_to_templates() -> None:
    prompt = build_prompt(
        auction_request(coins=10), "", PromptSettings(listing_limit=5)
    )
    user = prompt.messages[1].content
    assert prompt.numbered is None
    assert "- bid <0|1|2|3|4|5|6|7|8|9|10>" in user
    assert "Write one full legal action in notation." in user
    return


def test_templates_fold_final_tokens_of_a_factored_space() -> None:
    assert action_templates(UnlistableStepSpace()) == [
        "pass",
        "move a <1|2|3>",
        "move b <1|3>",
    ]
    return


def test_templates_shorten_long_option_lists() -> None:
    templates = action_templates(auction_request(coins=20).actions)
    assert templates == ["bid <0|1|2|3|4|5|6|7|8|9|10|11|...9 more>"]
    return


def test_old_events_beyond_the_cap_are_counted() -> None:
    events = tuple(Event("tick", f"tick {n}") for n in range(5))
    request = tic_tac_toe_request([], events)
    user = build_prompt(request, "", PromptSettings(max_recent_events=2)).messages[1]
    assert "(3 earlier events omitted)\n- tick 3\n- tick 4" in user.content
    return


def test_empty_recap_and_notes_are_explicit() -> None:
    user = build_prompt(tic_tac_toe_request([]), "", SETTINGS).messages[1].content
    assert "# Since your last decision\nNothing new." in user
    assert "# Your notes\n(empty)" in user
    return


def test_factored_request_prompt_uses_templates() -> None:
    request = replace(step_request(UnlistableStepSpace()), observation_text="board")
    user = build_prompt(request, "", SETTINGS).messages[1].content
    assert "- move a <1|2|3>" in user
    return


def test_retry_appends_reply_and_feedback() -> None:
    base = (Message("system", "s"), Message("user", "u"))
    messages = retry_messages(base, "z9", "'z9' is off the board.")
    assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
    assert "not accepted: 'z9' is off the board." in messages[-1].content
    return


def test_submit_tool_requires_action_and_states_memory_limit() -> None:
    tool = submit_tool(500)
    assert tool.parameters["required"] == ["reasoning", "action", "memory"]
    assert "at most 500 characters" in str(tool.parameters["properties"])
    return


def test_templates_at_exactly_the_limit_omit_nothing() -> None:
    actions = [(f"t{index}", "x") for index in range(MAX_TEMPLATE_LINES)]
    lines = action_templates(FlatActionSpace(actions, " ".join))
    assert len(lines) == MAX_TEMPLATE_LINES
    return


def test_recent_events_cap_of_zero_shows_no_event() -> None:
    request = tic_tac_toe_request([], events=(Event("e", "moved"),))
    text = recent_events_text(request, replace(PromptSettings(), max_recent_events=0))
    assert "moved" not in text
    return
