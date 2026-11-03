"""Prompts for LLM players: one fresh conversation per decision, never the full history.

The system message carries the rules and the answer format. The user message
carries the rendered state, events since the player's last decision, the
player's own notes, and the legal actions: numbered when few, as token
templates when too many to list.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from boardgames.agents.base import DecisionRequest
from boardgames.core import ActionSpace, Tokens, seat_label
from boardgames.llm.model import Message, ToolSpec

type OutputMode = Literal["tool", "text", "tools"]

TOOL_NAME = "submit_action"
MAX_TEMPLATE_OPTIONS = 12
MAX_TEMPLATE_LINES = 80
TOOLS_REMINDER = (
    "Use list_legal_actions to see your options and check_action to test one, "
    "then end by calling take_action."
)


@dataclass(frozen=True)
class PromptSettings:
    """`listing_limit` is the most actions numbered before templates replace them."""

    output_mode: OutputMode = "tool"
    listing_limit: int = 60
    memory_limit: int = 1500
    max_recent_events: int = 40
    persona: str | None = None


@dataclass(frozen=True)
class Prompt[A]:
    """Messages for one decision, and the actions in the order they were numbered."""

    messages: tuple[Message, ...]
    numbered: tuple[A, ...] | None


def submit_tool(memory_limit: int) -> ToolSpec:
    """The tool LLM players call to answer in tool mode."""
    return ToolSpec(
        name=TOOL_NAME,
        description="Submit your action for this decision.",
        parameters={
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Brief reasoning for the choice.",
                },
                "action": {
                    "type": "string",
                    "description": "One legal action, written in the game's notation.",
                },
                "memory": {
                    "type": "string",
                    "description": (
                        f"Your updated notes, at most {memory_limit} characters. "
                        "They replace your previous notes."
                    ),
                },
            },
            "required": ["reasoning", "action", "memory"],
        },
    )


def build_prompt[A](
    request: DecisionRequest[A], memory: str, settings: PromptSettings
) -> Prompt[A]:
    """System and user messages for one decision."""
    numbered = request.actions.listing(settings.listing_limit)
    system = system_message(request, settings)
    sections = [
        f"# State\n{request.observation_text}",
        f"# Since your last decision\n{recent_events_text(request, settings)}",
        f"# Your notes\n{memory or '(empty)'}",
        f"# Decision\n{request.decision.prompt}",
    ]
    if settings.output_mode == "tools":
        sections.append(TOOLS_REMINDER)
    else:
        sections.append(f"# Legal actions\n{actions_text(request, numbered)}")
    user = "\n\n".join(sections)
    return Prompt((Message("system", system), Message("user", user)), numbered)


def system_message[A](request: DecisionRequest[A], settings: PromptSettings) -> str:
    """Role, persona, rules and answer format."""
    seat = seat_label(request.decision.player)
    parts = [f"You are {seat}, a player in a game of {request.game_id}."]
    if settings.persona:
        parts.append(settings.persona)
    parts.append(f"# Rules\n{request.rules.strip()}")
    parts.append(f"# How to answer\n{answer_format(settings)}")
    return "\n\n".join(parts)


def answer_format(settings: PromptSettings) -> str:
    """Instructions for the chosen output mode."""
    if settings.output_mode == "tools":
        return (
            "Each decision shows the current state, what you saw happen since "
            "your last decision, your notes and the decision to make. Tools give "
            "you the rules, the state again, the legal actions and a check of any "
            "action. Your notes are the only memory you keep between decisions: "
            "use them for plans and observations about opponents, in at most "
            f"{settings.memory_limit} characters.\n\nCall tools as needed, then "
            "end by calling take_action with your brief reasoning, the action in "
            "notation, and your updated notes."
        )
    common = (
        "Each decision shows the current state, what you saw happen since your "
        "last decision, your notes, and the legal actions. Choose exactly one "
        "legal action and write it in notation, exactly as listed. Your notes "
        "are the only memory you keep between decisions: use them for plans and "
        f"observations about opponents, in at most {settings.memory_limit} characters."
    )
    if settings.output_mode == "tool":
        return (
            f"{common}\n\nAnswer by calling the {TOOL_NAME} tool with your brief "
            "reasoning, the action, and your updated notes."
        )
    return (
        f"{common}\n\nThink briefly, then end your reply with exactly these two "
        "lines:\nMemory: <your updated notes on one line>\nFinal Answer: <action>"
    )


def recent_events_text[A](request: DecisionRequest[A], settings: PromptSettings) -> str:
    """Bulleted events, most recent last; older ones beyond the cap are counted."""
    events = request.recent_events
    if not events:
        return "Nothing new."
    shown = events[-settings.max_recent_events :]
    lines = [f"- {event.text}" for event in shown]
    omitted = len(events) - len(shown)
    if omitted:
        lines.insert(0, f"({omitted} earlier events omitted)")
    return "\n".join(lines)


def actions_text[A](request: DecisionRequest[A], numbered: Sequence[A] | None) -> str:
    """Numbered actions with descriptions, or templates when there are too many."""
    if numbered is None:
        templates = action_templates(request.actions)
        lines = [f"- {template}" for template in templates]
        return (
            "There are too many legal actions to list. Every legal action matches "
            "one of these patterns, where <a|b> means one of the options:\n"
            + "\n".join(lines)
            + "\nWrite one full legal action in notation."
        )
    lines = []
    for index, action in enumerate(numbered, start=1):
        notation = request.actions.notation(action)
        description = request.action_text.describe_action(request.observation, action)
        detail = "" if description == notation else f" — {description}"
        lines.append(f"{index}. {notation}{detail}")
    example = request.actions.notation(numbered[0])
    return "\n".join(lines) + f'\nAnswer with the notation, for example "{example}".'


def action_templates[A](space: ActionSpace[A]) -> list[str]:
    """Patterns covering every legal action, folding final tokens into <a|b|c>."""
    lines: list[str] = []
    collect_templates(space, (), lines)
    if len(lines) >= MAX_TEMPLATE_LINES:
        lines = [*lines[:MAX_TEMPLATE_LINES], "(more patterns omitted)"]
    return lines


def collect_templates[A](
    space: ActionSpace[A], prefix: Tokens, lines: list[str]
) -> None:
    """Append template lines for the subtree under `prefix`, depth-first."""
    if len(lines) >= MAX_TEMPLATE_LINES:
        return
    if prefix and space.action_at(prefix) is not None:
        lines.append(" ".join(prefix))
    tokens = space.next_tokens(prefix)
    leaves = [t for t in tokens if not space.next_tokens((*prefix, t))]
    if len(leaves) == 1:
        lines.append(" ".join((*prefix, leaves[0])))
    elif leaves:
        shown = leaves[:MAX_TEMPLATE_OPTIONS]
        more = len(leaves) - len(shown)
        options = "|".join(shown) + (f"|...{more} more" if more else "")
        lines.append(" ".join((*prefix, f"<{options}>")))
    for token in tokens:
        if token not in leaves:
            collect_templates(space, (*prefix, token), lines)
    return


def retry_messages(
    messages: Sequence[Message], reply_text: str, feedback: str
) -> tuple[Message, ...]:
    """The conversation extended with the rejected reply and why it was rejected."""
    return (
        *messages,
        Message("assistant", reply_text or "(empty reply)"),
        Message(
            "user",
            f"Your answer was not accepted: {feedback}\n"
            "Choose again: exactly one legal action, in notation.",
        ),
    )
