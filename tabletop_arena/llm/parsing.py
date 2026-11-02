"""Turning a model reply into a legal action.

Two stages. `parse_reply` pulls the answer, reasoning and notes out of a tool
call or a "Final Answer:" line. `resolve_answer` maps the answer to a legal
action, trying in order: strict notation, soft match against listed actions,
the number of a listed action. `ActionExtractor` is an optional last resort
that asks a cheap model which listed action a reply meant.
"""

import difflib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tabletop_arena.agents import DecisionRequest
from tabletop_arena.core import NotationError
from tabletop_arena.llm.model import ChatModel, Completion, Message, ModelSettings

type ResolveMethod = Literal["strict", "soft", "number", "extractor"]
type RejectionKind = Literal["format", "illegal", "unmatched"]

FINAL_ANSWER = re.compile(r"final answer\s*:\s*(.+)", re.IGNORECASE)
MEMORY_LINE = re.compile(r"^\s*memory\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
CURLY_QUOTES = "".join(chr(code) for code in (0x2018, 0x2019, 0x201C, 0x201D))
DECORATION = re.compile(f"[`*\"'{CURLY_QUOTES}]")
EDGE_PUNCTUATION = ".,;:!?()[]{}<>"
SOFT_MATCH_LIMIT = 500
FUZZY_CUTOFF = 0.85


@dataclass(frozen=True)
class ParsedReply:
    answer: str
    reasoning: str | None
    memory: str | None


@dataclass(frozen=True)
class Resolved[A]:
    action: A
    method: ResolveMethod


@dataclass(frozen=True)
class Rejected:
    """Why an answer was not accepted; `feedback` is shown to the model on retry."""

    kind: RejectionKind
    feedback: str


def parse_reply(completion: Completion) -> ParsedReply | Rejected:
    """Answer, reasoning and notes from a tool call, else from the reply text."""
    if completion.tool_arguments is not None:
        return parse_tool_arguments(completion.tool_arguments)
    return parse_text(completion.text)


def parse_tool_arguments(arguments: str) -> ParsedReply | Rejected:
    """Fields of a submit_action call; a missing or empty action is rejected."""
    try:
        fields = json.loads(arguments)
    except json.JSONDecodeError:
        return Rejected("format", "The tool arguments were not valid JSON.")
    if not isinstance(fields, dict):
        return Rejected("format", "The tool arguments must be a JSON object.")
    action = fields.get("action")
    if not isinstance(action, str) or not action.strip():
        return Rejected("format", 'The tool call needs a non-empty "action" string.')
    return ParsedReply(
        answer=clean_answer(action),
        reasoning=optional_text(fields.get("reasoning")),
        memory=optional_text(fields.get("memory")),
    )


def optional_text(value: object) -> str | None:
    """A string field, or None when absent or not a string."""
    return value if isinstance(value, str) else None


def parse_text(text: str) -> ParsedReply | Rejected:
    """The last "Final Answer:" line, any "Memory:" line, and the text before them."""
    answers = FINAL_ANSWER.findall(text)
    memory = MEMORY_LINE.search(text)
    if answers:
        cut = min(
            position
            for position in (text.lower().rfind("final answer"), memory_start(memory))
            if position >= 0
        )
        return ParsedReply(
            answer=clean_answer(answers[-1]),
            reasoning=text[:cut].strip() or None,
            memory=memory.group(1).strip() if memory else None,
        )
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) == 1 and len(lines[0]) <= 40:
        return ParsedReply(answer=clean_answer(lines[0]), reasoning=None, memory=None)
    return Rejected("format", 'End your reply with a line "Final Answer: <action>".')


def memory_start(memory: re.Match[str] | None) -> int:
    """Where the "Memory:" line starts, or -1."""
    return -1 if memory is None else memory.start()


def clean_answer(text: str) -> str:
    """The answer without quotes, backticks, outer whitespace or end punctuation."""
    return DECORATION.sub("", text).strip().strip(EDGE_PUNCTUATION).strip()


def resolve_answer[A](
    answer: str, request: DecisionRequest[A], numbered: Sequence[A] | None
) -> Resolved[A] | Rejected:
    """The legal action an answer names, or why none was found."""
    actions = request.actions
    try:
        action = request.action_text.parse_action(answer)
    except NotationError:
        pass
    else:
        if actions.is_legal(action):
            return Resolved(action, "strict")
        return Rejected("illegal", actions.explain(action))
    candidates = actions.listing(SOFT_MATCH_LIMIT)
    if candidates is None:
        return unmatched(answer, None)
    soft = soft_match(answer, request, candidates)
    if soft is not None:
        return Resolved(soft, "soft")
    by_number = numbered_choice(answer, numbered, candidates, request)
    if by_number is not None:
        return Resolved(by_number, "number")
    return unmatched(answer, candidates[0] if candidates else None, request)


def soft_match[A](
    answer: str, request: DecisionRequest[A], candidates: Sequence[A]
) -> A | None:
    """A unique listed action the answer names despite case, wording or typos."""
    normalized = normalize(answer)
    notations = {normalize(request.actions.notation(a)): a for a in candidates}
    if normalized in notations:
        return notations[normalized]
    words = [word.strip(EDGE_PUNCTUATION) for word in normalized.split()]
    mentioned = [a for n, a in notations.items() if contains_tokens(words, n.split())]
    if len(mentioned) == 1:
        return mentioned[0]
    descriptions = {
        normalize(request.action_text.describe_action(request.observation, a)): a
        for a in candidates
    }
    if normalized in descriptions:
        return descriptions[normalized]
    close = difflib.get_close_matches(
        normalized, list(notations), n=2, cutoff=FUZZY_CUTOFF
    )
    if len(close) == 1:
        return notations[close[0]]
    return None


def normalize(text: str) -> str:
    """Lowercase with decoration removed and whitespace collapsed."""
    return " ".join(DECORATION.sub(" ", text).lower().split()).strip(EDGE_PUNCTUATION)


def contains_tokens(words: Sequence[str], tokens: Sequence[str]) -> bool:
    """Whether `tokens` appear in a row in `words`, or a lone word is a later token."""
    if not tokens:
        return False
    width = len(tokens)
    if any(list(words[i : i + width]) == list(tokens) for i in range(len(words))):
        return True
    return len(words) == 1 and words[0] in tokens and words[0] != tokens[0]


def numbered_choice[A](
    answer: str,
    numbered: Sequence[A] | None,
    candidates: Sequence[A],
    request: DecisionRequest[A],
) -> A | None:
    """The listed action at a 1-based number, if no notation uses that number itself."""
    if numbered is None or not answer.isdigit():
        return None
    if any(answer in request.actions.notation(a).split() for a in candidates):
        return None
    index = int(answer)
    return numbered[index - 1] if 1 <= index <= len(numbered) else None


def unmatched[A](
    answer: str, example: A | None, request: DecisionRequest[A] | None = None
) -> Rejected:
    """Rejection for an answer that names no legal action."""
    hint = ""
    if example is not None and request is not None:
        hint = f", for example {request.actions.notation(example)!r}"
    return Rejected(
        "unmatched",
        f"{answer!r} does not name a legal action. Write one action exactly as "
        f"listed{hint}.",
    )


class ActionExtractor:
    """Asks a cheap model which listed action a free-form reply chose."""

    def __init__(self, model: ChatModel, settings: ModelSettings) -> None:
        self._model = model
        self._settings = settings
        return

    async def extract[A](
        self, reply: str, request: DecisionRequest[A]
    ) -> "Extraction[A]":
        """The chosen listed action, or None, with the extractor's own completion."""
        candidates = request.actions.listing(SOFT_MATCH_LIMIT) or ()
        notations = [request.actions.notation(action) for action in candidates]
        prompt = (
            "A game player replied with the text below. Which one of the legal "
            "actions does it choose? Answer with that action exactly as written, "
            "or NONE if it chooses none of them.\n\n"
            f"Legal actions: {', '.join(notations)}\n\nReply:\n{reply}"
        )
        completion = await self._model.complete(
            [Message("user", prompt)], self._settings, None
        )
        answer = clean_answer(completion.text)
        if answer in notations:
            return Extraction(candidates[notations.index(answer)], completion)
        return Extraction(None, completion)


@dataclass(frozen=True)
class Extraction[A]:
    action: A | None
    completion: Completion
