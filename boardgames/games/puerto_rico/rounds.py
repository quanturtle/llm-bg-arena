"""Puerto Rico phase and round ends: refills, the next role picker and the winner."""

from dataclasses import replace

from boardgames.core import Event, PlayerId
from boardgames.games.puerto_rico.constants import (
    BUILDINGS,
    MAX_CITY_SPACES,
    TRADING_HOUSE_SPACES,
    Good,
)
from boardgames.games.puerto_rico.model import (
    PuertoRicoState,
    city_spaces_used,
    goods_from_list,
    goods_plus,
    goods_total,
    next_role_picker,
    next_unacted,
    total_points,
)


def _finish_settler(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    face_up_count = len(state.order) + 1
    discard = (*state.plantation_discard, *state.face_up)
    deck = state.plantation_deck
    rng = state.rng
    drawn = deck[:face_up_count]
    deck = deck[len(drawn) :]
    shuffled: tuple[Good, ...] = ()
    reshuffled = False
    if len(drawn) < face_up_count:
        shuffled, rng = rng.shuffled(discard)
        needed = face_up_count - len(drawn)
        drawn = (*drawn, *shuffled[:needed])
        deck = shuffled[needed:]
        discard = ()
        reshuffled = True
    events = [
        Event(
            "face_up_refilled",
            "The face-up plantations were replenished: " + ", ".join(drawn) + ".",
            {"drawn": list(drawn), "reshuffled": reshuffled},
        )
    ]
    if reshuffled:
        events.append(
            Event(
                "plantation_discard_reshuffled",
                "The plantation discard pile was shuffled into a new deck.",
                {"cards": len(shuffled)},
            )
        )
    state = replace(
        state,
        face_up=drawn,
        plantation_deck=deck,
        plantation_discard=discard,
        rng=rng,
    )
    return state, tuple(events)


def refill_colonist_ship(state: PuertoRicoState) -> PuertoRicoState:
    """Refill from supply: empty building slots, at least one per player."""
    empty_slots = 0
    for player in state.players:
        for building in player.buildings:
            spec = BUILDINGS[building.name]
            empty_slots += spec.max_colonists - building.colonists
    needed = max(empty_slots, len(state.order))
    refill = min(needed, state.colonist_supply)
    return replace(
        state,
        colonist_ship=refill,
        colonist_supply=state.colonist_supply - refill,
        colonist_shortage=refill < needed,
    )


def _finish_mayor(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    state = refill_colonist_ship(state)
    if not state.colonist_shortage:
        return state, ()
    return state, (
        Event(
            "colonist_shortage",
            "The colonist supply cannot refill the ship; the game will "
            "end at the end of this round.",
            {"ship": state.colonist_ship},
        ),
    )


def _finish_trader(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    if len(state.trading_house) < TRADING_HOUSE_SPACES:
        return state, ()
    supply = goods_plus(state.goods_supply, goods_from_list(list(state.trading_house)))
    return replace(state, trading_house=(), goods_supply=supply), ()


def tiebreak_key(state: PuertoRicoState, seat: PlayerId) -> tuple[int, int]:
    """Tie-break order after points: doubloons plus goods, then the governor."""
    player = state.players[seat]
    wealth = player.doubloons + goods_total(player.goods)
    governor = (
        state.final_governor if state.final_governor is not None else state.governor
    )
    distance = (state.order.index(seat) - state.order.index(governor)) % len(
        state.order
    )
    return wealth, -distance


def compute_winner(state: PuertoRicoState) -> PlayerId:
    """Highest score; ties go to the wealthier player, then to the governor."""
    best: PlayerId | None = None
    best_key: tuple[int, int, int] | None = None
    for seat in state.order:
        player = state.players[seat]
        key = (total_points(player), *tiebreak_key(state, seat))
        if best_key is None or key > best_key:
            best = seat
            best_key = key
    assert best is not None
    return best


def check_end_game(
    state: PuertoRicoState, *, final_governor: PlayerId | None = None
) -> PuertoRicoState:
    """Set game over when a supply runs out, a city fills or the round limit hits."""
    reason: str | None = None
    if state.vp_supply <= 0:
        reason = "victory point supply exhausted"
    elif state.colonist_shortage:
        reason = "colonist supply exhausted"
    elif any(city_spaces_used(player) >= MAX_CITY_SPACES for player in state.players):
        reason = "a player's city is full"
    elif state.config.max_rounds > 0 and state.round > state.config.max_rounds:
        reason = "round limit reached"
    if reason is None:
        return state
    state = replace(state, final_governor=final_governor)
    winner = compute_winner(state)
    return replace(
        state,
        phase="game_over",
        active_role=None,
        end_reason=reason,
        winner=winner,
    )


def end_round(state: PuertoRicoState) -> PuertoRicoState:
    """Add a doubloon to unchosen roles, pass the governorship and check the end."""
    roles = tuple(
        replace(
            role,
            doubloons=role.doubloons + (1 if role.taken_by is None else 0),
            taken_by=None,
        )
        for role in state.roles
    )
    governor_index = state.order.index(state.governor)
    final_governor = state.governor
    new_governor = state.order[(governor_index + 1) % len(state.order)]
    state = replace(
        state,
        roles=roles,
        governor=new_governor,
        round=state.round + 1,
        phase="role_selection",
        active_role=None,
        active_player=new_governor,
        players_acted=frozenset(),
        captain_passes=0,
    )
    return check_end_game(state, final_governor=final_governor)


def advance_role_picker(state: PuertoRicoState) -> PuertoRicoState:
    """Hand role selection to the next player, or end the round after the last."""
    next_picker = next_role_picker(state)
    if next_picker is None:
        return end_round(state)
    return replace(
        state,
        phase="role_selection",
        active_role=None,
        active_player=next_picker,
        players_acted=frozenset(),
        captain_passes=0,
    )


def finish_standard_phase(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    role = state.active_role
    if role == "settler":
        state, events = _finish_settler(state)
    elif role == "mayor":
        state, events = _finish_mayor(state)
    elif role == "trader":
        state, events = _finish_trader(state)
    else:
        events = ()
    return advance_role_picker(state), events


def mark_acted(
    state: PuertoRicoState, player: PlayerId
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    """Record that `player` acted; the last player to act finishes the phase."""
    acted = state.players_acted | {player}
    if len(acted) >= len(state.order):
        return finish_standard_phase(replace(state, players_acted=acted))
    next_player = next_unacted(replace(state, players_acted=acted), player)
    assert next_player is not None
    return (
        replace(state, players_acted=acted, active_player=next_player),
        (),
    )
