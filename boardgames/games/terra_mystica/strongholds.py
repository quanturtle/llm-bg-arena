"""Terra Mystica stronghold rewards, including the Darklings' worker trade."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.terra_mystica.constants import FactionType
from boardgames.games.terra_mystica.model import (
    Action,
    ChooseStrongholdPriests,
    TerraMysticaState,
    gain_power,
    priest_capacity,
    replace_at,
    replace_player,
    shipping_points,
)
from boardgames.games.terra_mystica.rounds import advance_turn


def stronghold_reward(
    state: TerraMysticaState,
    player: PlayerId,
    events: list[Event],
) -> tuple[TerraMysticaState, list[Event]]:
    """Apply a faction's one-time stronghold reward."""
    owner = state.players[player]
    profile = owner.profile
    if profile.type is FactionType.CULTISTS:
        owner = replace(owner, victory_points=owner.victory_points + 7)
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} scored 7 points from the stronghold.",
                {"player": player, "victory_points": 7},
            )
        )
    elif profile.type is FactionType.ALCHEMISTS:
        owner = replace(owner, resources=gain_power(owner.resources, 12))
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} gained 12 power from the stronghold.",
                {"player": player, "power": 12},
            )
        )
    elif profile.type is FactionType.MERMAIDS:
        if owner.shipping < profile.shipping_max:
            level = owner.shipping + 1
            owner = replace(
                owner,
                shipping=level,
                victory_points=owner.victory_points
                + shipping_points(level, profile.shipping_start),
            )
            events.append(
                Event(
                    "stronghold_reward",
                    f"{seat_label(player)} advanced to shipping {level} "
                    "and scored its points.",
                    {"player": player, "shipping": level},
                )
            )
        else:
            events.append(
                Event(
                    "stronghold_reward",
                    f"{seat_label(player)} is already at maximum shipping.",
                    {"player": player, "shipping": owner.shipping},
                )
            )
    elif profile.type is FactionType.HALFLINGS:
        owner = replace(
            owner,
            victory_points=owner.victory_points + 3 * profile.spade_vp_bonus,
        )
        state = replace_player(state, player, owner)
        state = replace(
            state,
            phase="cult_spades",
            cult_spades=replace_at(state.cult_spades, player, 3),
            spade_return="action",
            spade_actor=player,
            power_spade_tiles=(),
            spade_second=None,
            spade_topup=False,
            spade_require_all=True,
            active_player=player,
        )
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} gained 3 spades from the stronghold.",
                {"player": player, "spades": 3},
            )
        )
        return state, events
    elif profile.type is FactionType.DARKLINGS:
        state = replace(state, phase="stronghold_convert", active_player=player)
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} may trade up to three workers for priests.",
                {"player": player},
            )
        )
        return state, events
    state = replace_player(state, player, owner)
    return state, events


def choose_stronghold_priests(
    state: TerraMysticaState, player: PlayerId, workers: int
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    supply = priest_capacity(state, player) - owner.resources.priests
    maximum = max(0, min(3, owner.resources.workers, supply))
    if workers < 0 or workers > maximum:
        raise IllegalActionError(
            "the Darklings may trade at most three workers this way"
        )
    resources = replace(
        owner.resources,
        workers=owner.resources.workers - workers,
        priests=owner.resources.priests + workers,
    )
    owner = replace(owner, resources=resources)
    state = replace_player(state, player, owner)
    state = replace(state, phase="action", active_player=player)
    event = Event(
        "stronghold_convert",
        f"{seat_label(player)} traded {workers} worker(s) for priests as the "
        "Darklings' stronghold reward.",
        {"player": player, "workers": workers, "priests": workers},
    )
    return advance_turn(state, player, (event,))


def convert_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    supply = priest_capacity(state, player) - owner.resources.priests
    maximum = max(0, min(3, owner.resources.workers, supply))
    return [ChooseStrongholdPriests(workers) for workers in range(maximum + 1)]


def explain_convert(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    owner = state.players[player]
    supply = priest_capacity(state, player) - owner.resources.priests
    maximum = max(0, min(3, owner.resources.workers, supply))
    if isinstance(action, ChooseStrongholdPriests) and (
        action.workers < 0 or action.workers > maximum
    ):
        return "Trade at most three workers for priests."
    return "Choose how many workers to trade."
