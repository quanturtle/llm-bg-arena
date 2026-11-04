"""Match runner: plays one game with one agent per seat and logs every step.

Each round it asks every open decision's agent at once, from the same state,
then applies the answers in seat order. Agents see only their own observation
and the events visible to them since their last decision. Before each round it
waits while the match is paused; a cancelled match ends with match_stopped.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from functools import partial

from boardgames.agents import (
    Agent,
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
    Forfeited,
)
from boardgames.arena.clock import Clock
from boardgames.arena.control import AlwaysRunning, MatchControl
from boardgames.core import (
    ArenaError,
    ConfigError,
    Decision,
    Event,
    Game,
    GameConfig,
    PlayerId,
    Scores,
)
from boardgames.logs.schema import (
    DecisionRecord,
    ForfeitRecord,
    MatchFinished,
    MatchStarted,
    MatchStopped,
    ScoreRecord,
    SeatRecord,
    event_record,
    plain_object,
    trace_record,
)
from boardgames.logs.sink import RecordSink


class GameStuckError(ArenaError):
    """A non-terminal state has no open decision."""


class StepLimitError(ArenaError):
    """A match ran past its step limit without ending."""


class AgentContractError(ArenaError):
    """An agent returned an action that is not legal."""


@dataclass(frozen=True)
class MatchLimits:
    max_steps: int = 10_000


DEFAULT_LIMITS = MatchLimits()
ALWAYS_RUNNING = AlwaysRunning()


@dataclass(frozen=True)
class MatchResult:
    """Final game scores and ranks; forfeiters rank below everyone else."""

    match_id: str
    scores: Scores
    ranks: dict[PlayerId, int]
    forfeited: tuple[PlayerId, ...]
    steps: int


@dataclass(frozen=True)
class Progress[S]:
    """Where a match stands: state, step count, every event, and what each seat saw.

    `seen[p]` is how many events of `history` player p had been offered.
    """

    state: S
    step: int
    history: tuple[Event, ...]
    seen: tuple[int, ...]


@dataclass(frozen=True)
class Answer[A]:
    """A request an agent answered, the step of the state it saw, and its latency."""

    request: DecisionRequest[A]
    observed_at: int
    latency: float


@dataclass(frozen=True)
class UnfinishedDecision[A]:
    """A decision a failure or a stop cut short, with the model calls it paid for."""

    request: DecisionRequest[A]
    trace: DecisionTrace


@dataclass
class RoundLedger[S, A]:
    """A round in flight, read when a failure or a stop cuts it short.

    `progress` moves with each logged answer; agents report into `unfinished`.
    """

    progress: Progress[S]
    observed_at: int
    asked_at: float
    unfinished: list[UnfinishedDecision[A]] = field(default_factory=list)

    def watch(self, request: DecisionRequest[A]) -> DecisionRequest[A]:
        """`request`, reporting its paid calls to this round if it is cut short."""
        return replace(
            request, record_unfinished=partial(self.keep_unfinished, request)
        )

    def keep_unfinished(
        self, request: DecisionRequest[A], trace: DecisionTrace
    ) -> None:
        self.unfinished.append(UnfinishedDecision(request, trace))
        return


@dataclass(frozen=True)
class MatchContext[S, A, C: GameConfig]:
    """What stays fixed during a match."""

    game: Game[S, A, C]
    agents: tuple[Agent, ...]
    sink: RecordSink
    clock: Clock
    rules: str
    limits: MatchLimits


async def play_match[S, A, C: GameConfig](
    game: Game[S, A, C],
    config: C,
    seed: int,
    agents: Sequence[Agent],
    *,
    match_id: str,
    sink: RecordSink,
    clock: Clock,
    limits: MatchLimits = DEFAULT_LIMITS,
    control: MatchControl = ALWAYS_RUNNING,
) -> MatchResult:
    """Play one match to the end or to the first forfeit, writing the log to `sink`.

    Cancelling the call writes match_stopped and lets the cancellation through.
    """
    check_seats(config, agents)
    context = MatchContext(game, tuple(agents), sink, clock, game.rules_text(), limits)
    sink.write(start_record(context, config, seed, match_id))
    progress = set_up(context, config, seed)
    progress, forfeited = await play_rounds(context, progress, control)
    result = match_result(game, progress, forfeited, match_id)
    sink.write(finish_record(result, clock))
    return result


def check_seats(config: GameConfig, agents: Sequence[Agent]) -> None:
    """Raise ConfigError unless there is exactly one agent per seat."""
    if len(agents) != config.num_players:
        raise ConfigError(
            f"the game has {config.num_players} seats but {len(agents)} agents"
        )
    return


def start_record[S, A, C: GameConfig](
    context: MatchContext[S, A, C], config: C, seed: int, match_id: str
) -> MatchStarted:
    """The first log record: game, config, seed and who sits where."""
    return MatchStarted(
        match_id=match_id,
        game_id=context.game.id,
        config=plain_object(context.game.config_json(config)),
        seed=seed,
        seats=[
            SeatRecord(
                player=player,
                agent=agent.name,
                settings=plain_object(agent.settings()),
            )
            for player, agent in enumerate(context.agents)
        ],
        started_at=context.clock.now_iso(),
    )


def set_up[S, A, C: GameConfig](
    context: MatchContext[S, A, C], config: C, seed: int
) -> Progress[S]:
    """Run game setup and log its events as step 0."""
    transition = context.game.setup(config, seed)
    for event in transition.events:
        context.sink.write(event_record(0, event))
    return Progress(
        state=transition.state,
        step=0,
        history=transition.events,
        seen=(0,) * len(context.agents),
    )


async def play_rounds[S, A, C: GameConfig](
    context: MatchContext[S, A, C], progress: Progress[S], control: MatchControl
) -> tuple[Progress[S], tuple[PlayerId, ...]]:
    """Rounds until the end or a forfeit, waiting while paused.

    A cancellation or a failure, such as a model that stays unavailable, logs the
    paid calls of decisions it cut short and match_stopped at the last logged
    step, then propagates.
    """
    forfeited: tuple[PlayerId, ...] = ()
    ledger: RoundLedger[S, A] = RoundLedger(
        progress, progress.step, context.clock.monotonic()
    )
    try:
        while not context.game.is_terminal(progress.state) and not forfeited:
            await control.wait_until_resumed()
            ledger = RoundLedger(progress, progress.step, context.clock.monotonic())
            progress, forfeited = await play_round(context, ledger)
    except BaseException as error:
        record_unfinished_decisions(context, ledger, error)
        stopped = MatchStopped(
            steps=ledger.progress.step, stopped_at=context.clock.now_iso()
        )
        context.sink.write(stopped)
        raise
    return progress, forfeited


async def play_round[S, A, C: GameConfig](
    context: MatchContext[S, A, C], ledger: RoundLedger[S, A]
) -> tuple[Progress[S], tuple[PlayerId, ...]]:
    """Ask every open decision at once, then apply the answers in seat order.

    Each answer is logged as it applies, so `ledger.progress` moves with it.
    """
    progress = ledger.progress
    decisions = context.game.pending_decisions(progress.state)
    if not decisions:
        raise GameStuckError(f"no open decision at step {progress.step}")
    requests = [
        ledger.watch(request_for(context, progress, decision)) for decision in decisions
    ]
    progress = mark_seen(progress, decisions)
    ledger.progress = progress
    answers = await decide_together(context, decisions, requests)
    forfeited: list[PlayerId] = []
    for request, (choice, latency) in zip(requests, answers, strict=True):
        answer = Answer(request, ledger.observed_at, latency)
        if isinstance(choice, Forfeited):
            record_forfeit(context, progress, answer, choice)
            forfeited.append(request.decision.player)
        else:
            progress = apply_choice(context, progress, answer, choice)
            ledger.progress = progress
    return progress, tuple(forfeited)


async def decide_together[S, A, C: GameConfig](
    context: MatchContext[S, A, C],
    decisions: Sequence[Decision],
    requests: Sequence[DecisionRequest[A]],
) -> list[tuple[AgentChoice[A], float]]:
    """Ask every open decision at once; when one fails, cancel the rest."""
    tasks = [
        asyncio.ensure_future(
            timed_decide(context.agents[decision.player], request, context.clock)
        )
        for decision, request in zip(decisions, requests, strict=True)
    ]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def request_for[S, A, C: GameConfig](
    context: MatchContext[S, A, C], progress: Progress[S], decision: Decision
) -> DecisionRequest[A]:
    """The decision request for one player, built from their view only."""
    game = context.game
    observation = game.observe(progress.state, decision.player)
    unseen = progress.history[progress.seen[decision.player] :]
    return DecisionRequest(
        game_id=game.id,
        decision=decision,
        observation=observation,
        observation_text=game.render_text(observation),
        actions=game.legal_actions(progress.state, decision),
        recent_events=tuple(
            event for event in unseen if event.is_visible_to(decision.player)
        ),
        rules=context.rules,
        action_text=game,
    )


def mark_seen[S](progress: Progress[S], decisions: Sequence[Decision]) -> Progress[S]:
    """Record that the deciding players have been offered every event so far."""
    seen = list(progress.seen)
    for decision in decisions:
        seen[decision.player] = len(progress.history)
    return replace(progress, seen=tuple(seen))


async def timed_decide[A](
    agent: Agent, request: DecisionRequest[A], clock: Clock
) -> tuple[AgentChoice[A], float]:
    """The agent's choice and how many seconds it took."""
    started = clock.monotonic()
    choice = await agent.decide(request)
    return choice, clock.monotonic() - started


def record_unfinished_decisions[S, A, C: GameConfig](
    context: MatchContext[S, A, C], ledger: RoundLedger[S, A], error: BaseException
) -> None:
    """Log the paid model calls of each decision that `error` cut short."""
    latency = context.clock.monotonic() - ledger.asked_at
    for unfinished in ledger.unfinished:
        request = unfinished.request
        context.sink.write(
            ForfeitRecord(
                step=ledger.progress.step,
                observed_at_step=ledger.observed_at,
                player=request.decision.player,
                kind=request.decision.kind,
                reason=f"the decision failed: {error}",
                observation_digest=request.observation.digest(),
                latency_seconds=latency,
                trace=trace_record(unfinished.trace),
            )
        )
    return


def record_forfeit[S, A, C: GameConfig](
    context: MatchContext[S, A, C],
    progress: Progress[S],
    answer: Answer[A],
    choice: Forfeited,
) -> None:
    """Log a player giving up instead of answering."""
    request = answer.request
    context.sink.write(
        ForfeitRecord(
            step=progress.step,
            observed_at_step=answer.observed_at,
            player=request.decision.player,
            kind=request.decision.kind,
            reason=choice.reason,
            observation_digest=request.observation.digest(),
            latency_seconds=answer.latency,
            trace=trace_record(choice.trace),
        )
    )
    return


def apply_choice[S, A, C: GameConfig](
    context: MatchContext[S, A, C],
    progress: Progress[S],
    answer: Answer[A],
    choice: Chosen[A],
) -> Progress[S]:
    """Check and apply one chosen action, logging it and the events it caused."""
    game = context.game
    request = answer.request
    decision = request.decision
    if not request.actions.is_legal(choice.action):
        notation = game.format_action(choice.action)
        raise AgentContractError(
            f"{context.agents[decision.player].name} chose illegal {notation!r}"
        )
    transition = game.apply(progress.state, decision.player, choice.action)
    step = progress.step + 1
    if step > context.limits.max_steps:
        raise StepLimitError(f"match exceeded {context.limits.max_steps} steps")
    context.sink.write(
        DecisionRecord(
            step=step,
            observed_at_step=answer.observed_at,
            player=decision.player,
            kind=decision.kind,
            prompt=decision.prompt,
            observation_digest=request.observation.digest(),
            observation=plain_object(request.observation.data),
            action=game.format_action(choice.action),
            action_json=plain_object(game.action_json(choice.action)),
            latency_seconds=answer.latency,
            trace=trace_record(choice.trace),
        )
    )
    for event in transition.events:
        context.sink.write(event_record(step, event))
    return replace(
        progress,
        state=transition.state,
        step=step,
        history=(*progress.history, *transition.events),
    )


def match_result[S, A, C: GameConfig](
    game: Game[S, A, C],
    progress: Progress[S],
    forfeited: tuple[PlayerId, ...],
    match_id: str,
) -> MatchResult:
    """Scores from the game, with forfeiters moved below everyone else."""
    scores = game.scores(progress.state)
    return MatchResult(
        match_id=match_id,
        scores=scores,
        ranks=scores.ranks_after_forfeits(forfeited),
        forfeited=forfeited,
        steps=progress.step,
    )


def finish_record(result: MatchResult, clock: Clock) -> MatchFinished:
    """The last log record: points, final ranks and forfeits."""
    return MatchFinished(
        steps=result.steps,
        forfeited=list(result.forfeited),
        scores=[
            ScoreRecord(
                player=player,
                points=result.scores.points[player],
                rank=result.ranks[player],
                breakdown=dict(result.scores.breakdown.get(player, {})),
            )
            for player in sorted(result.scores.points)
        ],
        finished_at=clock.now_iso(),
    )
