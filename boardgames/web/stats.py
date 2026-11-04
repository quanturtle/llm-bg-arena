"""Statistics over match summaries: per-agent results, usage and Elo ratings.

Everything here is a pure function of a list of `MatchSummary`; only finished
matches and language model seats count, so bots get no rows or ratings. An
agent is identified by the name its seat recorded, so two runs of one model
with different settings share a row.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from boardgames.web.store import (
    AnyMatch,
    FinishedMatch,
    FinishedSeatSummary,
    add_cost,
)

ELO_START = 1000.0
ELO_K = 32.0


class Stat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentGameStats(Stat):
    """One agent's record at one game, or across games when `game_id` is None."""

    agent: str
    kind: str
    game_id: str | None
    # None when the row covers every prompt version
    prompt_version: int | None
    models: list[str]
    matches: int
    wins: int
    win_rate: float
    average_rank: float
    average_points: float
    forfeits: int
    decisions: int
    illegal_attempts: int
    illegal_rate: float
    fallbacks: int
    api_retries: int
    average_latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None
    cost_per_match: float | None
    elo: float | None


class HeadToHead(Stat):
    """How often an agent finished ahead of, level with or behind one opponent."""

    opponent: str
    matches: int
    ahead: int
    level: int
    behind: int


class Leaderboard(Stat):
    game_id: str | None
    prompt_version: int | None
    # versions among the game's finished matches, for choosing one
    prompt_versions: list[int]
    finished_matches: int
    rows: list[AgentGameStats]


class AgentDetail(Stat):
    agent: str
    kind: str
    overall: AgentGameStats | None
    games: list[AgentGameStats]
    # one row per prompt version, across games
    prompts: list[AgentGameStats]
    opponents: list[HeadToHead]


@dataclass
class Tally:
    """Running sums for one agent at one game, and the models it played with."""

    kind: str = "unknown"
    matches: int = 0
    models: set[str] = field(default_factory=set)
    wins: int = 0
    rank_sum: int = 0
    points_sum: float = 0.0
    forfeits: int = 0
    decisions: int = 0
    illegal_attempts: int = 0
    fallbacks: int = 0
    api_retries: int = 0
    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = 0.0

    def add(self, seat: FinishedSeatSummary, won_outright: bool) -> None:
        self.kind = seat.kind
        self.matches += 1
        if seat.model is not None:
            self.models.add(seat.model)
        self.wins += won_outright
        self.rank_sum += seat.rank or 0
        self.points_sum += seat.points or 0.0
        self.forfeits += seat.forfeited
        self.decisions += seat.decisions
        self.illegal_attempts += seat.illegal_attempts
        self.fallbacks += seat.fallbacks
        self.api_retries += seat.api_retries
        self.latency_seconds += seat.latency_seconds
        self.prompt_tokens += seat.prompt_tokens
        self.completion_tokens += seat.completion_tokens
        self.cost_usd = add_cost(self.cost_usd, seat.cost_usd)
        return


@dataclass
class Ratings:
    """Elo per agent at one game, updated match by match in play order."""

    values: dict[str, float] = field(default_factory=dict)

    def rating(self, agent: str) -> float:
        return self.values.get(agent, ELO_START)

    def update(self, match: FinishedMatch) -> None:
        """Each pair of model seats plays one Elo game; a seat's change is the mean."""
        seats = model_seats(match)
        if len(seats) < 2:
            return
        changes: defaultdict[str, float] = defaultdict(float)
        for first in seats:
            for second in seats:
                if first.player == second.player:
                    continue
                gap = (self.rating(second.agent) - self.rating(first.agent)) / 400
                expected = 1 / (1 + 10**gap)
                delta = ELO_K * (score_against(first, second) - expected)
                changes[first.agent] += delta / (len(seats) - 1)
        for agent, change in changes.items():
            self.values[agent] = self.rating(agent) + change
        return


def score_against(seat: FinishedSeatSummary, other: FinishedSeatSummary) -> float:
    """1 when `seat` finished ahead of `other`, 0.5 level, 0 behind."""
    if seat.rank < other.rank:
        return 1.0
    return 0.5 if seat.rank == other.rank else 0.0


def model_seats(match: FinishedMatch) -> list[FinishedSeatSummary]:
    """The language model seats of a match; bots are left out of statistics."""
    return [seat for seat in match.seats if seat.kind == "llm"]


def finished_in_order(matches: Iterable[AnyMatch]) -> list[FinishedMatch]:
    """Finished matches, oldest first, the order ratings are built in."""
    finished = [m for m in matches if isinstance(m, FinishedMatch)]
    return sorted(finished, key=lambda m: (m.started_at, m.match_id))


def ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def stats_row(
    agent: str,
    game_id: str | None,
    prompt_version: int | None,
    tally: Tally,
    elo: float | None,
) -> AgentGameStats:
    return AgentGameStats(
        agent=agent,
        kind=tally.kind,
        game_id=game_id,
        prompt_version=prompt_version,
        matches=tally.matches,
        wins=tally.wins,
        win_rate=ratio(tally.wins, tally.matches),
        average_rank=ratio(tally.rank_sum, tally.matches),
        average_points=ratio(tally.points_sum, tally.matches),
        models=sorted(tally.models),
        forfeits=tally.forfeits,
        decisions=tally.decisions,
        illegal_attempts=tally.illegal_attempts,
        illegal_rate=ratio(tally.illegal_attempts, tally.decisions),
        fallbacks=tally.fallbacks,
        api_retries=tally.api_retries,
        average_latency_seconds=ratio(tally.latency_seconds, tally.decisions),
        prompt_tokens=tally.prompt_tokens,
        completion_tokens=tally.completion_tokens,
        cost_usd=tally.cost_usd,
        cost_per_match=None
        if tally.cost_usd is None
        else ratio(tally.cost_usd, tally.matches),
        elo=elo,
    )


def leaderboard(
    matches: Sequence[AnyMatch],
    game_id: str | None,
    prompt_version: int | None = None,
) -> Leaderboard:
    """Rows per model agent at `game_id` by Elo; across all games (None) by win rate.

    A `prompt_version` keeps only the matches played with that prompt."""
    of_game = [
        m
        for m in finished_in_order(matches)
        if game_id in (None, m.game_id) and model_seats(m)
    ]
    finished = [m for m in of_game if prompt_version in (None, m.prompt_version)]
    tallies: defaultdict[str, Tally] = defaultdict(Tally)
    ratings = Ratings()
    for match in finished:
        sole_winner = len(match.winners()) == 1
        for seat in model_seats(match):
            tallies[seat.agent].add(seat, won_outright=sole_winner and seat.rank == 1)
        if game_id is not None:
            ratings.update(match)
    rows = [
        stats_row(
            agent,
            game_id,
            prompt_version,
            tally,
            ratings.rating(agent) if game_id else None,
        )
        for agent, tally in tallies.items()
    ]
    rows.sort(
        key=lambda row: (-(row.elo or 0.0), -row.win_rate, row.average_rank, row.agent)
    )
    return Leaderboard(
        game_id=game_id,
        prompt_version=prompt_version,
        prompt_versions=sorted({m.prompt_version for m in of_game}),
        finished_matches=len(finished),
        rows=rows,
    )


def head_to_head(matches: Sequence[AnyMatch], agent: str) -> list[HeadToHead]:
    """Finished matches of `agent` against each other agent, most played first."""
    records: dict[str, dict[str, int]] = {}
    for match in finished_in_order(matches):
        for seat in match.seats:
            if seat.agent != agent:
                continue
            for other in match.seats:
                if other.player == seat.player or other.agent == agent:
                    continue
                record = records.setdefault(
                    other.agent, {"ahead": 0, "level": 0, "behind": 0}
                )
                outcome = score_against(seat, other)
                record[
                    "ahead"
                    if outcome == 1.0
                    else "level"
                    if outcome == 0.5
                    else "behind"
                ] += 1
    rows = [
        HeadToHead(opponent=opponent, matches=sum(record.values()), **record)
        for opponent, record in records.items()
    ]
    rows.sort(key=lambda row: (-row.matches, row.opponent))
    return rows


def agent_detail(matches: Sequence[AnyMatch], agent: str) -> AgentDetail:
    """The agent's overall row, one row per game it played, and head-to-head records."""
    played = [m for m in matches if any(seat.agent == agent for seat in m.seats)]
    game_ids = sorted({m.game_id for m in played})
    # Ratings need every match at the game, not only the agent's own, or they
    # disagree with the leaderboard built over the whole store.
    games = [
        row
        for game_id in game_ids
        for row in leaderboard(matches, game_id).rows
        if row.agent == agent
    ]
    overall = next(
        (row for row in leaderboard(matches, None).rows if row.agent == agent), None
    )
    prompts = [
        row
        for version in sorted({m.prompt_version for m in played})
        for row in leaderboard(matches, None, version).rows
        if row.agent == agent
    ]
    kind = (
        overall.kind
        if overall
        else next(
            (s.kind for m in played for s in m.seats if s.agent == agent), "unknown"
        )
    )
    return AgentDetail(
        agent=agent,
        kind=kind,
        overall=overall,
        games=games,
        prompts=prompts,
        opponents=head_to_head(played, agent),
    )
