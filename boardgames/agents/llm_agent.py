"""LlmAgent: an LLM player that answers in notation, retries rejections, keeps notes.

Per decision: build a fresh prompt, call the model, parse and resolve the reply.
A rejected answer is re-prompted with the reason ("b2 is already taken by X")
up to `max_illegal_retries` times; after that the fallback policy applies.
In "tools" mode the model instead calls game tools in a loop driven by the
state machine in llm/tools.py, and ends by calling take_action. Every model
call is recorded in the decision trace.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from boardgames.agents.base import (
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
    FallbackPolicy,
    Forfeited,
)
from boardgames.agents.random_agent import uniform_action
from boardgames.core import JsonObject, JsonValue, Rng
from boardgames.llm.model import (
    ChatModel,
    Completion,
    ForcedTool,
    Message,
    ModelSettings,
    ToolChoice,
    ToolSpec,
    messages_json,
)
from boardgames.llm.parsing import (
    ActionExtractor,
    ParsedReply,
    Rejected,
    Resolved,
    parse_reply,
    resolve_answer,
)
from boardgames.llm.prompting import (
    PromptSettings,
    build_prompt,
    retry_messages,
    submit_tool,
)
from boardgames.llm.tools import (
    NO_TOOL_NUDGE,
    DecisionProgress,
    ToolBudget,
    ToolResult,
    after_text_reply,
    after_tool_calls,
    answer_tool_calls,
    game_tools,
)


@dataclass(frozen=True)
class LlmAgentSettings:
    """After `max_illegal_retries` rejected re-prompts, `fallback` picks the action.

    The "default" fallback plays the decision's default (such as pass), else random.
    `max_tool_calls` caps one decision's tool calls in "tools" mode.
    """

    model: ModelSettings
    prompt: PromptSettings = field(default_factory=PromptSettings)
    max_illegal_retries: int = 3
    max_tool_calls: int = 12
    fallback: FallbackPolicy = "random"
    label: str | None = None


@dataclass(frozen=True)
class Attempt[A]:
    """One model call: how its reply resolved, plus its log record and completions.

    `resolution` is None for a tools-mode round that only looked things up.
    `rejections` counts the rejected answers in the call: at most one in a
    single-shot mode, one per rejected take_action in tools mode.
    """

    resolution: Resolved[A] | Rejected | None
    reply: ParsedReply | None
    record: dict[str, JsonValue]
    completions: tuple[Completion, ...]
    rejections: int


class LlmAgent:
    """An LLM player for one seat; its notes persist across decisions of a match."""

    def __init__(
        self,
        model: ChatModel,
        settings: LlmAgentSettings,
        seed: int,
        extractor: ActionExtractor | None = None,
    ) -> None:
        self._model = model
        self._settings = settings
        self._seed = seed
        self._rng = Rng.seeded(seed)
        self._extractor = extractor
        self._memory = ""
        return

    @property
    def name(self) -> str:
        return self._settings.label or self._settings.model.model

    @property
    def memory(self) -> str:
        return self._memory

    def settings(self) -> dict[str, JsonValue]:
        prompt = self._settings.prompt
        return {
            "kind": "llm",
            "model": self._settings.model.to_json(),
            "output_mode": prompt.output_mode,
            "listing_limit": prompt.listing_limit,
            "memory_limit": prompt.memory_limit,
            "max_recent_events": prompt.max_recent_events,
            "persona": prompt.persona,
            "max_illegal_retries": self._settings.max_illegal_retries,
            "max_tool_calls": self._settings.max_tool_calls,
            "fallback": self._settings.fallback,
            "extractor": self._extractor.model_name if self._extractor else None,
            "seed": self._seed,
        }

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        if self._settings.prompt.output_mode == "tools":
            return await self._decide_with_tools(request)
        return await self._decide_single_shot(request)

    async def _decide_single_shot[A](
        self, request: DecisionRequest[A]
    ) -> AgentChoice[A]:
        """One answer per model call; a rejected answer is re-prompted."""
        prompt_settings = self._settings.prompt
        prompt = build_prompt(request, self._memory, prompt_settings)
        tools: tuple[ToolSpec, ...] = ()
        tool_choice: ToolChoice = "auto"
        if prompt_settings.output_mode == "tool":
            tools = (submit_tool(prompt_settings.memory_limit),)
            tool_choice = ForcedTool(tools[0].name)
        messages: tuple[Message, ...] = prompt.messages
        logged = 0
        attempts: list[Attempt[A]] = []
        for _ in range(self._settings.max_illegal_retries + 1):
            completion = await self._model.complete(
                messages, self._settings.model, tools, tool_choice
            )
            attempt = await self._interpret(
                completion, request, prompt.numbered, messages[logged:]
            )
            logged = len(messages)
            attempts.append(attempt)
            if isinstance(attempt.resolution, Resolved):
                self._remember(attempt.reply)
                reasoning = attempt.reply.reasoning if attempt.reply else None
                trace = decision_trace(attempts, reasoning, self._memory, None)
                return Chosen(attempt.resolution.action, trace)
            if isinstance(attempt.resolution, Rejected):
                feedback = attempt.resolution.feedback
                messages = retry_messages(messages, reply_text(completion), feedback)
        return self._fall_back(request, attempts)

    async def _decide_with_tools[A](
        self, request: DecisionRequest[A]
    ) -> AgentChoice[A]:
        """Rounds of tool calls until take_action is accepted or the budget ends."""
        prompt_settings = self._settings.prompt
        prompt = build_prompt(request, self._memory, prompt_settings)
        tools = game_tools(prompt_settings)
        budget = ToolBudget(
            self._settings.max_tool_calls, self._settings.max_illegal_retries
        )
        messages: tuple[Message, ...] = prompt.messages
        logged = 0
        progress: DecisionProgress[A] = DecisionProgress()
        attempts: list[Attempt[A]] = []
        while progress.phase == "exploring":
            completion = await self._model.complete(
                messages, self._settings.model, tools, "auto"
            )
            results = answer_tool_calls(completion.tool_calls, request, prompt_settings)
            if results:
                progress = after_tool_calls(progress, results, budget)
                messages = (*messages, *tool_round_messages(completion, results))
            else:
                progress = after_text_reply(progress, budget)
                messages = (*messages, *nudge_messages(completion))
            attempts.append(tool_round_attempt(completion, results, messages[logged:]))
            logged = len(messages)
        if progress.chosen is not None:
            self._remember(progress.reply)
            reasoning = progress.reply.reasoning if progress.reply else None
            trace = decision_trace(attempts, reasoning, self._memory, None)
            return Chosen(progress.chosen.action, trace)
        return self._fall_back(request, attempts)

    async def _interpret[A](
        self,
        completion: Completion,
        request: DecisionRequest[A],
        numbered: Sequence[A] | None,
        new_messages: Sequence[Message],
    ) -> Attempt[A]:
        """Parse and resolve one reply, asking the extractor when matching fails."""
        reply = parse_reply(completion)
        parsed: ParsedReply | None = None
        resolution: Resolved[A] | Rejected
        if isinstance(reply, Rejected):
            resolution = reply
        else:
            parsed = reply
            resolution = resolve_answer(reply.answer, request, numbered)
        completions = [completion]
        if (
            isinstance(resolution, Rejected)
            and resolution.kind != "illegal"
            and self._extractor is not None
        ):
            extraction = await self._extractor.extract(reply_text(completion), request)
            completions.append(extraction.completion)
            if extraction.action is not None:
                resolution = Resolved(extraction.action, "extractor")
        record = {
            "messages": messages_json(new_messages),
            **attempt_record(completion, parsed, resolution, completions[1:]),
        }
        rejections = 1 if isinstance(resolution, Rejected) else 0
        return Attempt(resolution, parsed, record, tuple(completions), rejections)

    def _remember(self, reply: ParsedReply | None) -> None:
        """Replace the notes with the reply's notes, cut to the memory limit."""
        if reply is not None and reply.memory is not None:
            self._memory = reply.memory[: self._settings.prompt.memory_limit]
        return

    def _fall_back[A](
        self, request: DecisionRequest[A], attempts: list[Attempt[A]]
    ) -> AgentChoice[A]:
        """Apply the fallback policy once every attempt was rejected."""
        policy = self._settings.fallback
        if policy == "forfeit":
            trace = decision_trace(attempts, None, self._memory, "forfeit")
            return Forfeited(f"no legal action after {len(attempts)} attempts", trace)
        default = request.actions.default if policy == "default" else None
        if default is not None:
            return Chosen(
                default, decision_trace(attempts, None, self._memory, "default")
            )
        action, self._rng = uniform_action(request.actions, self._rng)
        return Chosen(action, decision_trace(attempts, None, self._memory, "random"))


def reply_text(completion: Completion) -> str:
    """What the model answered: its tool arguments if it called the tool, else text."""
    if completion.tool_arguments is not None:
        return completion.tool_arguments
    return completion.text


def tool_round_messages[A](
    completion: Completion, results: Sequence[ToolResult[A]]
) -> tuple[Message, ...]:
    """The assistant turn with its calls, then one tool turn per answered call."""
    assistant = Message("assistant", completion.text, tool_calls=completion.tool_calls)
    answers = [
        Message("tool", result.text, tool_call_id=call.id)
        for call, result in zip(completion.tool_calls, results, strict=True)
    ]
    return (assistant, *answers)


def nudge_messages(completion: Completion) -> tuple[Message, Message]:
    """A text-only reply echoed back with the reminder to call a tool."""
    return (
        Message("assistant", completion.text or "(empty reply)"),
        Message("user", NO_TOOL_NUDGE),
    )


def tool_round_attempt[A](
    completion: Completion,
    results: Sequence[ToolResult[A]],
    new_messages: Sequence[Message],
) -> Attempt[A]:
    """Log one round of tool calls; a round without a call is a format rejection.

    The record's resolution is the accepted action, else the first rejection.
    """
    resolved = [result for result in results if isinstance(result.outcome, Resolved)]
    rejected = [result for result in results if isinstance(result.outcome, Rejected)]
    decisive = resolved[0] if resolved else (rejected[0] if rejected else None)
    resolution = decisive.outcome if decisive is not None else None
    reply = decisive.reply if decisive is not None else None
    rejections = len(rejected)
    if not results:
        resolution = Rejected("format", NO_TOOL_NUDGE)
        rejections = 1
    calls: list[JsonValue] = [
        {"name": call.name, "arguments": call.arguments, "result": result.text}
        for call, result in zip(completion.tool_calls, results, strict=True)
    ]
    record: dict[str, JsonValue] = {
        "messages": messages_json(new_messages),
        **attempt_record(completion, reply, resolution, ()),
        "tool_calls": calls,
    }
    return Attempt(resolution, reply, record, (completion,), rejections)


def attempt_record[A](
    completion: Completion,
    reply: ParsedReply | None,
    resolution: Resolved[A] | Rejected | None,
    extractor_completions: Sequence[Completion],
) -> dict[str, JsonValue]:
    """Log form of one attempt's reply and how it resolved."""
    rejection: JsonValue = None
    if isinstance(resolution, Rejected):
        rejection = {"kind": resolution.kind, "feedback": resolution.feedback}
    return {
        "text": completion.text,
        "tool_arguments": completion.tool_arguments,
        "model_reasoning": completion.reasoning,
        "answer": reply.answer if reply else None,
        "resolved_by": resolution.method if isinstance(resolution, Resolved) else None,
        "rejection": rejection,
        "prompt_tokens": completion.usage.prompt_tokens,
        "completion_tokens": completion.usage.completion_tokens,
        "cost_usd": completion.cost_usd,
        "api_retries": completion.api_retries,
        "is_cached": completion.is_cached,
        "extractor_calls": len(extractor_completions),
    }


def decision_trace[A](
    attempts: Sequence[Attempt[A]],
    reasoning: str | None,
    memory: str,
    fallback: FallbackPolicy | None,
) -> DecisionTrace:
    """Totals over every model and extractor call of a decision."""
    completions = [c for attempt in attempts for c in attempt.completions]
    costs = [c.cost_usd for c in completions]
    records: tuple[JsonObject, ...] = tuple(attempt.record for attempt in attempts)
    return DecisionTrace(
        reasoning=reasoning,
        memory=memory,
        attempts=records,
        illegal_attempts=sum(attempt.rejections for attempt in attempts),
        api_retries=sum(c.api_retries for c in completions),
        fallback=fallback,
        prompt_tokens=sum(c.usage.prompt_tokens for c in completions),
        completion_tokens=sum(c.usage.completion_tokens for c in completions),
        cost_usd=None if None in costs else sum(c for c in costs if c is not None),
    )
