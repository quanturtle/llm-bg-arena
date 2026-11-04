"""Log upgrade: re-record a match's game output under the current rules.

The recorded moves are replayed from the seed. Events, observations, decision
prompts, notation and final scores are recomputed; agent traces and thoughts
stay as recorded. A log whose moves the current rules reject cannot be upgraded.
"""

from collections.abc import Sequence
from typing import Any

from boardgames.core import (
    AnyGame,
    ArenaError,
    Decision,
    IllegalActionError,
    NotationError,
    PlayerId,
    Transition,
    create_game,
)
from boardgames.logs.replay import first_record, replay_match
from boardgames.logs.schema import (
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
    event_record,
    plain_object,
    score_records,
)


class LogUpgradeError(ArenaError):
    """A recorded move is not open or not legal under the current rules."""


def upgrade_records(records: Sequence[LogRecord]) -> list[LogRecord]:
    """The log re-recorded under the current rules; a current log comes back as is.

    The result replays exactly, or LogUpgradeError names the first rejected move.
    """
    start = first_record(records, MatchStarted)
    game = create_game(start.game_id)
    if start.rules_version == game.rules_version:
        return list(records)
    upgraded = rerecord(game, start, records)
    replay_match(upgraded)
    return upgraded


def rerecord(
    game: AnyGame, start: MatchStarted, records: Sequence[LogRecord]
) -> list[LogRecord]:
    """Every record rebuilt from the seed and the recorded moves, in log order."""
    setup = game.setup(game.parse_config(start.config), start.seed)
    states: dict[int, Any] = {0: setup.state}
    upgraded: list[LogRecord] = [
        start.model_copy(update={"rules_version": game.rules_version})
    ]
    upgraded.extend(event_record(0, event) for event in setup.events)
    forfeited: list[PlayerId] = []
    for record in records:
        if isinstance(record, DecisionRecord):
            decision, transition = rerecord_decision(game, states, record)
            states[record.step] = transition.state
            upgraded.append(decision)
            upgraded.extend(event_record(record.step, e) for e in transition.events)
        elif isinstance(record, ForfeitRecord):
            upgraded.append(rerecord_forfeit(game, states, record))
            forfeited.append(PlayerId(record.player))
        elif isinstance(record, MatchFinished):
            upgraded.append(rescore(game, states[max(states)], record, forfeited))
        elif not isinstance(record, MatchStarted | EventRecord):
            upgraded.append(record)
    return upgraded


def rerecord_decision(
    game: AnyGame, states: dict[int, Any], record: DecisionRecord
) -> tuple[DecisionRecord, Transition[Any]]:
    """The decision with its prompt, observation and notation recomputed, and the
    transition its recorded move makes under the current rules."""
    player = PlayerId(record.player)
    seen = states[record.observed_at_step]
    decision = open_decision(game, seen, player, record.step)
    observation = game.observe(seen, player)
    try:
        action = game.parse_action(record.action)
        transition = game.apply(states[record.step - 1], player, action)
    except (NotationError, IllegalActionError) as error:
        raise LogUpgradeError(
            f"step {record.step}: the current rules reject {record.action!r}: {error}"
        ) from error
    upgraded = record.model_copy(
        update={
            "kind": decision.kind,
            "prompt": decision.prompt,
            "observation_digest": observation.digest(),
            "observation": plain_object(observation.data),
            "action": game.format_action(action),
            "action_json": plain_object(game.action_json(action)),
        }
    )
    return upgraded, transition


def open_decision(game: AnyGame, state: Any, player: PlayerId, step: int) -> Decision:
    """The player's open decision in `state` under the current rules."""
    for decision in game.pending_decisions(state):
        if decision.player == player:
            return decision
    raise LogUpgradeError(
        f"step {step}: P{player + 1} has no open decision under the current rules"
    )


def rerecord_forfeit(
    game: AnyGame, states: dict[int, Any], record: ForfeitRecord
) -> ForfeitRecord:
    """The forfeit with the digest of what the player sees under the current rules."""
    observation = game.observe(states[record.observed_at_step], PlayerId(record.player))
    return record.model_copy(update={"observation_digest": observation.digest()})


def rescore(
    game: AnyGame, state: Any, finish: MatchFinished, forfeited: Sequence[PlayerId]
) -> MatchFinished:
    """The finish record with points and ranks from the current rules."""
    scores = game.scores(state)
    ranks = scores.ranks_after_forfeits(forfeited)
    return finish.model_copy(update={"scores": score_records(scores, ranks)})
