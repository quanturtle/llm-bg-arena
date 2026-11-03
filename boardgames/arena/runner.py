"""Match runner: plays one game with one agent per seat and logs every step.

Each round it asks every open decision's agent at once, from the same state,
then applies the answers in seat order. Agents see only their own observation
and the events visible to them since their last decision.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace

from boardgames.agents import (
    Agent,
    AgentChoice,
    Chosen,
    DecisionRequest,
    Forfeited,
)
from boardgames.arena.clock import Clock
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
) -> MatchResult:
    """Play one match to the end or to the first forfeit, writing the log to `sink`."""
    check_seats(config, agents)
    context = MatchContext(game, tuple(agents), sink, clock, game.rules_text(), limits)
    sink.write(start_record(context, config, seed, match_id))
    progress = set_up(context, config, seed)
    forfeited: tuple[PlayerId, ...] = ()
    while not game.is_terminal(progress.state) and not forfeited:
        progress, forfeited = await play_round(context, progress)
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


async def play_round[S, A, C: GameConfig](
    context: MatchContext[S, A, C], progress: Progress[S]
) -> tuple[Progress[S], tuple[PlayerId, ...]]:
    """Ask every open decision at once, then apply the answers in seat order."""
    decisions = context.game.pending_decisions(progress.state)
    if not decisions:
        raise GameStuckError(f"no open decision at step {progress.step}")
    requests = [request_for(context, progress, decision) for decision in decisions]
    progress = mark_seen(progress, decisions)
    answers = await asyncio.gather(
        *(
            timed_decide(context.agents[decision.player], request, context.clock)
            for decision, request in zip(decisions, requests, strict=True)
        )
    )
    observed_at = progress.step
    forfeited: list[PlayerId] = []
    for request, (choice, latency) in zip(requests, answers, strict=True):
        answer = Answer(request, observed_at, latency)
        if isinstance(choice, Forfeited):
            record_forfeit(context, progress, answer, choice)
            forfeited.append(request.decision.player)
        else:
            progress = apply_choice(context, progress, answer, choice)
    return progress, tuple(forfeited)


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
