"""Terra Mystica round flow: income, turn order, passing and the cult bonus."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
    seats,
)
from boardgames.games.terra_mystica.bonus import (
    bonus_income,
    bonus_pass_vp,
    check_bonus_choice,
)
from boardgames.games.terra_mystica.constants import (
    BONUS_CARDS,
    STANDARD_DWELLING_INCOME,
    STANDARD_TEMPLE_INCOME,
    STANDARD_TRADING_HOUSE_INCOME,
    BuildingType,
    CultBonus,
    FactionType,
    Income,
    ScoringAction,
    ScoringTile,
)
from boardgames.games.terra_mystica.model import (
    Board,
    PlayerState,
    TerraMysticaState,
    add_income,
    building_counts,
    cap_priests,
    cult_bonus_json,
    favor_income,
    favor_pass_vp,
    gain_power,
    income_with_power,
    replace_player,
)
from boardgames.games.terra_mystica.scoring import final_scores
from boardgames.games.terra_mystica.spade_gain import gain_spade_power


def round_tile(state: TerraMysticaState) -> ScoringTile:
    return state.scoring[state.round - 1]


def round_scoring(state: TerraMysticaState) -> ScoringAction:
    return round_tile(state).action


def bonus_text(bonus: CultBonus) -> str:
    return f"{bonus.amount} {bonus.reward} per {bonus.per} {bonus.cult.value}"


def income_for(board: Board, seat: PlayerId, player: PlayerState) -> Income:
    profile = player.profile
    counts = building_counts(board, seat)
    dwellings = counts[BuildingType.DWELLING]
    trading = counts[BuildingType.TRADING_HOUSE]
    temples = counts[BuildingType.TEMPLE]
    sanctuaries = counts[BuildingType.SANCTUARY]
    strongholds = counts[BuildingType.STRONGHOLD]

    dwelling_income = (
        Income()
        if dwellings == 0
        else (profile.dwelling_income or STANDARD_DWELLING_INCOME)[dwellings - 1]
    )
    trading_income = (
        Income()
        if trading == 0
        else (profile.trading_house_income or STANDARD_TRADING_HOUSE_INCOME)[
            trading - 1
        ]
    )
    temple_income = (
        Income()
        if temples == 0
        else (profile.temple_income or STANDARD_TEMPLE_INCOME)[temples - 1]
    )
    sanctuary_income = profile.sanctuary_income if sanctuaries else Income()
    stronghold_income = profile.stronghold_income if strongholds else Income()
    favor = favor_income(player)
    bonus = bonus_income(player)
    return Income(
        coins=(
            profile.base_income.coins
            + dwelling_income.coins
            + trading_income.coins
            + temple_income.coins
            + sanctuary_income.coins
            + stronghold_income.coins
            + favor.coins
            + bonus.coins
        ),
        workers=(
            profile.base_income.workers
            + dwelling_income.workers
            + trading_income.workers
            + temple_income.workers
            + sanctuary_income.workers
            + stronghold_income.workers
            + favor.workers
            + bonus.workers
        ),
        priests=(
            profile.base_income.priests
            + dwelling_income.priests
            + trading_income.priests
            + temple_income.priests
            + sanctuary_income.priests
            + stronghold_income.priests
            + favor.priests
            + bonus.priests
        ),
        power=(
            profile.base_income.power
            + dwelling_income.power
            + trading_income.power
            + temple_income.power
            + sanctuary_income.power
            + stronghold_income.power
            + favor.power
            + bonus.power
        ),
        victory_points=profile.base_income.victory_points,
    )


def start_round(
    state: TerraMysticaState,
) -> tuple[TerraMysticaState, tuple[Event, ...]]:
    """Enter the action phase and run the income phase."""
    round_number = state.round
    tile = round_tile(state)
    state = replace(
        state,
        phase="action",
        active_player=state.order[0],
        passed=frozenset(),
        pass_order=(),
        used_power_actions=frozenset(),
        cult_spades=(0,) * len(state.players),
        spade_return="round",
        spade_actor=None,
        power_spade_tiles=(),
        spade_second=None,
        spade_transformed=(),
        spade_intermediate=False,
        spade_reach_used=False,
        spade_topup=True,
        spade_require_all=False,
        pending_favors=0,
        pending_town=False,
        pending_town_position=None,
        pending_town_river=None,
        pending_power=(),
        power_actor=None,
        used_special_actions=frozenset(),
        extra_actions=0,
        cultist_offered=False,
        cultist_taken=False,
        cultist_actor=None,
        pending_towns=0,
    )
    events: list[Event] = [
        Event(
            "round_started",
            f"Round {round_number}: {tile.action.value} scores; "
            f"cult bonus {bonus_text(tile.bonus)}.",
            {
                "round": round_number,
                "scoring": tile.action.value,
                "bonus": cult_bonus_json(tile.bonus),
            },
        )
    ]
    for seat in state.order:
        owner = state.players[seat]
        income = income_for(state.board, seat, owner)
        resources = cap_priests(state, seat, income_with_power(owner.resources, income))
        owner = replace(
            owner,
            resources=resources,
            victory_points=owner.victory_points + income.victory_points,
        )
        state = replace_player(state, seat, owner)
        events.append(
            Event(
                "income",
                f"{seat_label(seat)} collects income.",
                {
                    "player": seat,
                    "coins": income.coins,
                    "workers": income.workers,
                    "priests": income.priests,
                    "power": income.power,
                    "victory_points": income.victory_points,
                },
            )
        )
    return state, tuple(events)


def _cult_bonus_amount(player: PlayerState, bonus: CultBonus) -> int:
    return (player.cult(bonus.cult) // bonus.per) * bonus.amount


def next_cult_spade_player(state: TerraMysticaState) -> PlayerId | None:
    return next((seat for seat in state.order if state.cult_spades[seat] > 0), None)


def start_next_round(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    """Finish cleanup and begin the next round."""
    state = replace(
        state,
        round=state.round + 1,
        passed=frozenset(),
        pass_order=(),
        used_power_actions=frozenset(),
        active_player=state.order[0],
        cult_spades=(0,) * len(state.players),
        spade_return="round",
        spade_actor=None,
        power_spade_tiles=(),
        spade_second=None,
        spade_transformed=(),
        spade_intermediate=False,
        spade_reach_used=False,
        spade_topup=True,
        spade_require_all=False,
        pending_favors=0,
        pending_town=False,
        pending_town_position=None,
        pending_town_river=None,
        pending_power=(),
        power_actor=None,
        used_special_actions=frozenset(),
        extra_actions=0,
        cultist_offered=False,
        cultist_taken=False,
        cultist_actor=None,
        pending_towns=0,
        bonus_coins=tuple(
            coins + (1 if index in state.bonus_available else 0)
            for index, coins in enumerate(state.bonus_coins)
        ),
    )
    state, round_events = start_round(state)
    return Transition(state, (*events, *round_events))


def cult_spade_event(
    state: TerraMysticaState, player: PlayerId, bonus: CultBonus
) -> Event:
    return Event(
        "cult_bonus",
        f"{seat_label(player)} may use {state.cult_spades[player]} "
        "cult-bonus spade(s).",
        {
            "player": player,
            "cult": bonus.cult.value,
            "reward": bonus.reward,
            "amount": state.cult_spades[player],
        },
    )


def _apply_cult_bonus(
    state: TerraMysticaState, seat: PlayerId, bonus: CultBonus
) -> tuple[TerraMysticaState, Event | None]:
    """Pay one non-spade end-of-round cult bonus to one player."""
    owner = state.players[seat]
    amount = _cult_bonus_amount(owner, bonus)
    if amount <= 0:
        return state, None
    if bonus.reward == "priests":
        resources = cap_priests(
            state, seat, add_income(owner.resources, Income(priests=amount))
        )
        owner = replace(owner, resources=resources)
    elif bonus.reward == "workers":
        resources = add_income(owner.resources, Income(workers=amount))
        owner = replace(owner, resources=resources)
    elif bonus.reward == "coins":
        resources = add_income(owner.resources, Income(coins=amount))
        owner = replace(owner, resources=resources)
    elif bonus.reward == "power":
        resources = gain_power(owner.resources, amount)
        owner = replace(owner, resources=resources)
    elif bonus.reward == "spades":
        raise ValueError("spades need a player's choice")
    state = replace_player(state, seat, owner)
    event = Event(
        "cult_bonus",
        f"{seat_label(seat)} gained {amount} {bonus.reward} from the "
        f"{bonus.cult.value} cult bonus.",
        {
            "player": seat,
            "cult": bonus.cult.value,
            "reward": bonus.reward,
            "amount": amount,
        },
    )
    return state, event


def end_round(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    if state.round >= state.config.rounds:
        state = replace(state, phase="game_over", end_reason="after the final round")
        final = final_scores(state)
        best = max(points for points, _ in final.values())
        winners = [seat for seat, (points, _) in final.items() if points == best]
        names = ", ".join(seat_label(seat) for seat in winners)
        game_over = Event(
            "game_over",
            f"Game over: {names} with {best} points.",
            {
                "winners": winners,
                "scores": [
                    {
                        "player": seat,
                        "points": final[seat][0],
                        "breakdown": final[seat][1],
                    }
                    for seat in seats(len(state.players))
                ],
            },
        )
        return Transition(state, (*events, game_over))
    first = state.pass_order[0]
    start = state.order.index(first)
    new_order = (*state.order[start:], *state.order[:start])
    state = replace(state, order=new_order)
    bonus = round_tile(state).bonus
    if bonus.reward == "spades":
        budgets = tuple(
            _cult_bonus_amount(state.players[seat], bonus)
            for seat in range(len(state.players))
        )
        for seat, budget in enumerate(budgets):
            owner = state.players[seat]
            if owner.profile.type is FactionType.HALFLINGS:
                state = replace_player(
                    state,
                    PlayerId(seat),
                    replace(
                        owner,
                        victory_points=owner.victory_points
                        + budget * owner.profile.spade_vp_bonus,
                    ),
                )
            state = gain_spade_power(state, PlayerId(seat), budget)
        state = replace(
            state,
            phase="cult_spades",
            cult_spades=budgets,
            spade_return="round",
            spade_actor=None,
            power_spade_tiles=(),
            spade_second=None,
            spade_transformed=(),
            spade_intermediate=False,
            spade_reach_used=False,
            spade_topup=True,
            spade_require_all=False,
        )
        next_player = next_cult_spade_player(state)
        if next_player is None:
            return start_next_round(state, events)
        event = cult_spade_event(state, next_player, bonus)
        return Transition(replace(state, active_player=next_player), (*events, event))
    bonus_events: list[Event] = []
    for seat in new_order:
        state, bonus_event = _apply_cult_bonus(state, seat, bonus)
        if bonus_event is not None:
            bonus_events.append(bonus_event)
    return start_next_round(state, (*events, *bonus_events))


def _next_unpassed(state: TerraMysticaState, player: PlayerId) -> PlayerId:
    index = state.order.index(player)
    for offset in range(1, len(state.order) + 1):
        candidate = state.order[(index + offset) % len(state.order)]
        if candidate not in state.passed:
            return candidate
    return player


def _finish_pass(
    state: TerraMysticaState, player: PlayerId, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    state = replace(state, phase="action")
    if len(state.passed) >= len(state.players):
        return end_round(state, events)
    next_player = _next_unpassed(state, player)
    state = replace(state, active_player=next_player)
    return Transition(state, events)


def pass_turn(
    state: TerraMysticaState, player: PlayerId
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    trading = state.board.count(player, BuildingType.TRADING_HOUSE)
    favor_vp = favor_pass_vp(owner, trading)
    bonus_vp = bonus_pass_vp(state, player)
    bridge_vp = 0
    if (
        owner.profile.type is FactionType.ENGINEERS
        and state.board.count(player, BuildingType.STRONGHOLD) > 0
    ):
        for bridge in state.bridges:
            if bridge.owner != player:
                continue
            first = state.board.tile(bridge.first)
            second = state.board.tile(bridge.second)
            if (
                first is not None
                and first.building is not None
                and first.building.owner == player
                and second is not None
                and second.building is not None
                and second.building.owner == player
            ):
                bridge_vp += 3
    card = owner.bonus_card
    victory_points = owner.victory_points + favor_vp + bonus_vp + bridge_vp
    owner = replace(owner, victory_points=victory_points, bonus_card=None)
    state = replace_player(state, player, owner)
    passed = state.passed | {player}
    pass_order = (*state.pass_order, player)
    text = f"{seat_label(player)} passed"
    if favor_vp:
        text += f" and gained {favor_vp} VP from a favor tile"
    if bonus_vp:
        text += f" and gained {bonus_vp} VP from a bonus card"
    if bridge_vp:
        text += f" and gained {bridge_vp} VP from bridges"
    event = Event(
        "passed",
        text + ".",
        {
            "player": player,
            "favor_vp": favor_vp,
            "bonus_vp": bonus_vp,
            "bridge_vp": bridge_vp,
            "bonus_card": card,
        },
    )
    available = state.bonus_available
    if card is not None and card not in available:
        available = (*available, card)
    state = replace(
        state,
        passed=passed,
        pass_order=pass_order,
        bonus_available=available,
        bonus_returned=card,
        extra_actions=0,
    )
    if state.config.bonus_cards and state.round < state.config.rounds and available:
        state = replace(
            state,
            phase="bonus_choice",
            pending_bonus=True,
            bonus_mode="pass",
            active_player=player,
        )
        return Transition(state, (event,))
    return _finish_pass(state, player, (event,))


def begin_bonus_draft(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    """Start the initial bonus-card draft after the starting dwellings."""
    queue = tuple(reversed(state.order))
    state = replace(
        state,
        phase="bonus_choice",
        pending_bonus=True,
        bonus_mode="setup",
        bonus_queue=queue,
        bonus_returned=None,
        active_player=queue[0],
    )
    event = Event(
        "bonus_draft",
        f"{seat_label(queue[0])} takes the first bonus card.",
        {"player": queue[0]},
    )
    return Transition(state, (*events, event))


def take_bonus_card(
    state: TerraMysticaState, player: PlayerId, index: int
) -> Transition[TerraMysticaState]:
    """Take an available bonus card, then continue the draft or the pass."""
    check_bonus_choice(state, player)
    if index not in state.bonus_available or index == state.bonus_returned:
        raise IllegalActionError("that bonus card is not available")
    owner = state.players[player]
    coins = state.bonus_coins[index]
    owner = replace(
        owner,
        bonus_card=index,
        resources=replace(owner.resources, coins=owner.resources.coins + coins),
    )
    state = replace_player(state, player, owner)
    available = tuple(card for card in state.bonus_available if card != index)
    coins_left = list(state.bonus_coins)
    coins_left[index] = 0
    state = replace(
        state,
        bonus_available=available,
        bonus_coins=tuple(coins_left),
    )
    event = Event(
        "bonus_card",
        f"{seat_label(player)} took bonus card {index} ({BONUS_CARDS[index].label}).",
        {"player": player, "bonus_card": index, "coins": coins},
    )
    if state.bonus_mode == "setup":
        queue = state.bonus_queue[1:]
        if queue:
            return Transition(
                replace(
                    state,
                    bonus_queue=queue,
                    active_player=queue[0],
                    bonus_returned=None,
                ),
                (event,),
            )
        coins_left = [
            coins + (1 if index in available else 0)
            for index, coins in enumerate(state.bonus_coins)
        ]
        state = replace(
            state,
            pending_bonus=False,
            bonus_mode=None,
            bonus_queue=(),
            bonus_returned=None,
            bonus_coins=tuple(coins_left),
        )
        state, round_events = start_round(state)
        return Transition(state, (event, *round_events))
    state = replace(
        state,
        pending_bonus=False,
        bonus_mode=None,
        bonus_returned=None,
    )
    return _finish_pass(state, player, (event,))


def advance_turn(
    state: TerraMysticaState,
    player: PlayerId,
    events: tuple[Event, ...],
) -> Transition[TerraMysticaState]:
    if state.pending_power:
        gain = state.pending_power[0]
        return Transition(
            replace(state, phase="power_gain", active_player=gain.player), events
        )
    if state.extra_actions > 0 and player not in state.passed:
        return Transition(replace(state, extra_actions=state.extra_actions - 1), events)
    unpassed = [seat for seat in state.order if seat not in state.passed]
    if unpassed == [player]:
        return Transition(state, events)
    next_player = _next_unpassed(state, player)
    return Transition(replace(state, active_player=next_player), events)
