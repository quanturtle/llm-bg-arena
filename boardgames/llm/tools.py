"""Game tools for LLM players, and the state machine that drives one decision.

Pattern: State Machine. A decision starts in "exploring". The model reads the
state, rules, events and legal actions through tools, may check an action, and
ends by calling take_action. A legal take_action moves to "committed". Too many
calls, too many rejected actions or repeated text-only replies move to
"exhausted", where the agent's fallback policy applies. Every function here is
pure: tools answer from the DecisionRequest alone.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from boardgames.agents.base import DecisionRequest
from boardgames.core import ActionSpace, JsonObject, NotationError, Tokens
from boardgames.llm.model import ToolCall, ToolSpec
from boardgames.llm.parsing import (
    ParsedReply,
    Rejected,
    Resolved,
    parse_tool_arguments,
    resolve_answer,
)
from boardgames.llm.prompting import (
    PromptSettings,
    actions_text,
    recent_events_text,
    submit_tool,
)

type Phase = Literal["exploring", "committed", "exhausted"]

TAKE_ACTION = "take_action"
NO_ARGUMENTS: JsonObject = {"type": "object", "properties": {}}
MAX_CONTINUATIONS = 40
NO_TOOL_NUDGE = (
    "Reply by calling a tool. End the decision by calling take_action with "
    "one legal action in notation."
)


def game_tools(settings: PromptSettings) -> tuple[ToolSpec, ...]:
    """The six tools of a decision; take_action takes submit_action's fields."""
    take_action = replace(
        submit_tool(settings.memory_limit),
        name=TAKE_ACTION,
        description=(
            "Take your action for this decision. A legal action ends the decision; "
            "an illegal one is explained so you can try again."
        ),
    )
    return (
        ToolSpec(
            "get_state", "The current state of the game as you see it.", NO_ARGUMENTS
        ),
        ToolSpec("get_rules", "The rules of the game.", NO_ARGUMENTS),
        ToolSpec(
            "get_recent_events",
            "What happened since your last decision.",
            NO_ARGUMENTS,
        ),
        ToolSpec(
            "list_legal_actions",
            "Legal actions now. Without a prefix: every action when there are few "
            "enough, else the first tokens. With a prefix (the first tokens of an "
            "action in notation): the tokens that can follow it.",
            {
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "description": "First tokens of an action, or empty.",
                    }
                },
            },
        ),
        ToolSpec(
            "check_action",
            "Whether an action in notation is legal now, and why not if it is not.",
            {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action in notation."}
                },
                "required": ["action"],
            },
        ),
        take_action,
    )


@dataclass(frozen=True)
class ToolResult[A]:
    """What the model sees; `outcome` and `reply` are set only by take_action."""

    text: str
    outcome: Resolved[A] | Rejected | None = None
    reply: ParsedReply | None = None


def answer_tool_call[A](
    call: ToolCall, request: DecisionRequest[A], settings: PromptSettings
) -> ToolResult[A]:
    """The result of one tool call; bad names or arguments give an error text."""
    if call.name == TAKE_ACTION:
        return take_action_result(call.arguments, request, settings)
    arguments = parse_arguments(call.arguments)
    if arguments is None:
        return ToolResult("The tool arguments must be a JSON object.")
    if call.name == "get_state":
        return ToolResult(request.observation_text)
    if call.name == "get_rules":
        return ToolResult(request.rules)
    if call.name == "get_recent_events":
        return ToolResult(recent_events_text(request, settings))
    if call.name == "list_legal_actions":
        prefix = string_argument(arguments, "prefix")
        return ToolResult(legal_actions_text(request, prefix, settings))
    if call.name == "check_action":
        return ToolResult(
            check_action_text(request, string_argument(arguments, "action"))
        )
    names = ", ".join(tool.name for tool in game_tools(settings))
    return ToolResult(f"Unknown tool {call.name!r}. The tools are: {names}.")


def parse_arguments(text: str) -> JsonObject | None:
    """Tool arguments as a JSON object; an empty string is an empty object."""
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def string_argument(arguments: JsonObject, key: str) -> str:
    """A string argument, or empty when missing or not a string."""
    value = arguments.get(key)
    return value if isinstance(value, str) else ""


def legal_actions_text[A](
    request: DecisionRequest[A], prefix: str, settings: PromptSettings
) -> str:
    """Numbered actions for a small space without a prefix; else the next tokens."""
    tokens = tuple(prefix.split())
    if not tokens:
        numbered = request.actions.listing(settings.listing_limit)
        if numbered is not None:
            return actions_text(request, numbered)
    return continuation_text(request.actions, tokens)


def continuation_text[A](space: ActionSpace[A], tokens: Tokens) -> str:
    """Whether `tokens` is a complete action, and which tokens can follow it."""
    prefix = " ".join(tokens)
    lines = []
    if tokens and space.action_at(tokens) is not None:
        lines.append(f"{prefix!r} is a complete legal action.")
    following = space.next_tokens(tokens)
    if following:
        shown = ", ".join(following[:MAX_CONTINUATIONS])
        more = len(following) - MAX_CONTINUATIONS
        if more > 0:
            shown += f" and {more} more"
        lead = f"Tokens that can follow {prefix!r}" if tokens else "First tokens"
        lines.append(f"{lead}: {shown}.")
    if not lines:
        return f"No legal action starts with {prefix!r}."
    return "\n".join(lines)


def check_action_text[A](request: DecisionRequest[A], text: str) -> str:
    """Legal, illegal with the reason, or not valid notation."""
    try:
        action = request.action_text.parse_action(text)
    except NotationError as error:
        return f"Not valid notation: {error}"
    if request.actions.is_legal(action):
        return f"{request.actions.notation(action)!r} is legal."
    return f"Not legal: {request.actions.explain(action)}"


def take_action_result[A](
    arguments: str, request: DecisionRequest[A], settings: PromptSettings
) -> ToolResult[A]:
    """Resolve a take_action call like a submit_action reply."""
    reply = parse_tool_arguments(arguments)
    if isinstance(reply, Rejected):
        return ToolResult(f"Not accepted: {reply.feedback}", outcome=reply)
    numbered = request.actions.listing(settings.listing_limit)
    resolution = resolve_answer(reply.answer, request, numbered)
    if isinstance(resolution, Rejected):
        text = f"Not accepted: {resolution.feedback}"
        return ToolResult(text, outcome=resolution, reply=reply)
    notation = request.actions.notation(resolution.action)
    return ToolResult(f"Accepted: {notation}", outcome=resolution, reply=reply)


@dataclass(frozen=True)
class ToolBudget:
    """Limits that move a decision to "exhausted"."""

    max_tool_calls: int
    max_illegal_retries: int


@dataclass(frozen=True)
class DecisionProgress[A]:
    """Where a decision stands; `chosen` and `reply` are set once committed."""

    phase: Phase = "exploring"
    calls_made: int = 0
    rejections: int = 0
    text_replies: int = 0
    chosen: Resolved[A] | None = None
    reply: ParsedReply | None = None


def after_tool_calls[A](
    progress: DecisionProgress[A],
    results: Sequence[ToolResult[A]],
    budget: ToolBudget,
) -> DecisionProgress[A]:
    """Progress after one reply's tool calls, answered in order."""
    for result in results:
        progress = after_tool_call(progress, result, budget)
        if progress.phase != "exploring":
            break
    return progress


def after_tool_call[A](
    progress: DecisionProgress[A], result: ToolResult[A], budget: ToolBudget
) -> DecisionProgress[A]:
    """Progress after one answered tool call."""
    calls_made = progress.calls_made + 1
    if isinstance(result.outcome, Resolved):
        return replace(
            progress,
            phase="committed",
            calls_made=calls_made,
            chosen=result.outcome,
            reply=result.reply,
        )
    rejected = isinstance(result.outcome, Rejected)
    rejections = progress.rejections + (1 if rejected else 0)
    advanced = replace(progress, calls_made=calls_made, rejections=rejections)
    return exhausted_if_over(advanced, budget)


def after_text_reply[A](
    progress: DecisionProgress[A], budget: ToolBudget
) -> DecisionProgress[A]:
    """Progress after a reply with no tool call; the second one exhausts."""
    advanced = replace(progress, text_replies=progress.text_replies + 1)
    return exhausted_if_over(advanced, budget)


def exhausted_if_over[A](
    progress: DecisionProgress[A], budget: ToolBudget
) -> DecisionProgress[A]:
    """The progress, moved to "exhausted" once any limit is reached."""
    over = (
        progress.calls_made >= budget.max_tool_calls
        or progress.rejections > budget.max_illegal_retries
        or progress.text_replies > 1
    )
    return replace(progress, phase="exhausted") if over else progress
