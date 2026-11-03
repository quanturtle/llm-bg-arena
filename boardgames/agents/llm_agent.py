"""LlmAgent: an LLM player that answers in notation, retries rejections, keeps notes.

Per decision: build a fresh prompt, call the model, parse and resolve the reply.
A rejected answer is re-prompted with the reason ("b2 is already taken by X")
up to `max_illegal_retries` times; after that the fallback policy applies.
Every attempt is recorded in the decision trace.
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
    Message,
    ModelSettings,
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


@dataclass(frozen=True)
class LlmAgentSettings:
    """After `max_illegal_retries` rejected re-prompts, `fallback` picks the action.

    The "default" fallback plays the decision's default (such as pass), else random.
    """

    model: ModelSettings
    prompt: PromptSettings = field(default_factory=PromptSettings)
    max_illegal_retries: int = 3
    fallback: FallbackPolicy = "random"
    label: str | None = None


@dataclass(frozen=True)
class Attempt[A]:
    """One model call: how its reply resolved, plus its log record and completions."""

    resolution: Resolved[A] | Rejected
    reply: ParsedReply | None
    record: dict[str, JsonValue]
    completions: tuple[Completion, ...]


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
            "fallback": self._settings.fallback,
            "extractor": self._extractor.model_name if self._extractor else None,
            "seed": self._seed,
        }

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        prompt_settings = self._settings.prompt
        prompt = build_prompt(request, self._memory, prompt_settings)
        tool = None
        if prompt_settings.output_mode == "tool":
            tool = submit_tool(prompt_settings.memory_limit)
        messages: tuple[Message, ...] = prompt.messages
        logged = 0
        attempts: list[Attempt[A]] = []
        for _ in range(self._settings.max_illegal_retries + 1):
            completion = await self._model.complete(
                messages, self._settings.model, tool
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
            feedback = attempt.resolution.feedback
            messages = retry_messages(messages, reply_text(completion), feedback)
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
        return Attempt(resolution, parsed, record, tuple(completions))

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


def attempt_record[A](
    completion: Completion,
    reply: ParsedReply | None,
    resolution: Resolved[A] | Rejected,
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
        illegal_attempts=sum(
            1 for attempt in attempts if isinstance(attempt.resolution, Rejected)
        ),
        api_retries=sum(c.api_retries for c in completions),
        fallback=fallback,
        prompt_tokens=sum(c.usage.prompt_tokens for c in completions),
        completion_tokens=sum(c.usage.completion_tokens for c in completions),
        cost_usd=None if None in costs else sum(c for c in costs if c is not None),
    )
