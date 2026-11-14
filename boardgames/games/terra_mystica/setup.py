"""Terra Mystica setup: the config check, the opening state and starting dwellings."""

from dataclasses import replace
from typing import Literal

from boardgames.core import (
    ConfigError,
    Event,
    IllegalActionError,
    PlayerId,
    Rng,
    Transition,
    seat_label,
)
from boardgames.games.terra_mystica.constants import (
    BONUS_CARD_COUNTS,
    BONUS_CARDS,
    FACTION_BY_TYPE,
    FACTIONS_BY_TERRAIN,
    FIXED_FACTIONS,
    SCORING_TILES,
    TERRAIN_WHEEL,
    VARIABLE_START_VP,
    BuildingType,
    FactionType,
    ScoringAction,
)
from boardgames.games.terra_mystica.model import (
    Action,
    Board,
    BuildDwelling,
    Building,
    ChooseFaction,
    Hex,
    PlayerState,
    TerraMysticaConfig,
    TerraMysticaState,
    cult_bonus_json,
    replace_player,
)
from boardgames.games.terra_mystica.rounds import (
    begin_bonus_draft,
    bonus_text,
    start_round,
)


def check_config(config: TerraMysticaConfig) -> None:
    if not 2 <= config.num_players <= 5:
        raise ConfigError(
            f"Terra Mystica needs 2 to 5 players, got {config.num_players}"
        )
    if not 1 <= config.rounds <= 6:
        raise ConfigError(f"rounds must be from 1 to 6, got {config.rounds}")
    return


def _starting_victory_points(config: TerraMysticaConfig, faction: FactionType) -> int:
    if not config.variable_points:
        return 20
    return VARIABLE_START_VP.get(faction, 20)


def initial_setup_queue(
    order: tuple[PlayerId, ...], players: tuple[PlayerState, ...]
) -> tuple[PlayerId, ...]:
    """Clockwise first, counterclockwise second, then Nomads and Chaos Magicians."""
    first = tuple(
        seat for seat in order if players[seat].profile.starting_dwellings > 1
    )
    second = tuple(reversed(first))
    extras = tuple(
        seat
        for seat in order
        for _ in range(max(0, players[seat].profile.starting_dwellings - 2))
    )
    chaos = tuple(
        seat for seat in order if players[seat].profile.starting_dwellings == 1
    )
    return (*first, *second, *extras, *chaos)


def _player_state(config: TerraMysticaConfig, faction: FactionType) -> PlayerState:
    profile = FACTION_BY_TYPE[faction]
    return PlayerState(
        faction=faction,
        resources=profile.starting_resources,
        victory_points=_starting_victory_points(config, faction),
        cults=profile.starting_cults,
        shipping=profile.shipping_start,
        digging=profile.digging_start,
    )


def start_game(config: TerraMysticaConfig, seed: int) -> Transition[TerraMysticaState]:
    rng = Rng.seeded(seed)
    n = config.num_players
    first_seat, rng = rng.below(n)
    order: tuple[PlayerId, ...] = tuple(
        PlayerId((first_seat + offset) % n) for offset in range(n)
    )
    if config.fixed_setup:
        factions = list(FIXED_FACTIONS[n])
    else:
        terrains, rng = rng.shuffled(TERRAIN_WHEEL)
        factions = []
        for terrain in terrains[:n]:
            options = FACTIONS_BY_TERRAIN[terrain]
            choice, rng = rng.below(len(options))
            factions.append(options[choice])
    while True:
        scoring_order, rng = rng.shuffled(SCORING_TILES)
        late = scoring_order[4 : config.rounds]
        if not any(tile.action is ScoringAction.SPADE for tile in late):
            break
    scoring = scoring_order[: config.rounds]

    player_states = tuple(_player_state(config, faction) for faction in factions)
    bonus_available: tuple[int, ...] = ()
    if config.bonus_cards:
        deck, rng = rng.shuffled(tuple(range(len(BONUS_CARDS))))
        bonus_available = tuple(deck[: BONUS_CARD_COUNTS[n - 2]])

    phase: Literal["faction_choice", "setup"]
    if config.faction_choice and not config.fixed_setup:
        setup_queue: tuple[PlayerId, ...] = ()
        faction_queue = order
        phase = "faction_choice"
        active_player = order[0]
    else:
        setup_queue = initial_setup_queue(order, player_states)
        faction_queue = ()
        phase = "setup"
        active_player = setup_queue[0]

    state = TerraMysticaState(
        config=config,
        rng=rng,
        board=Board.base(),
        players=player_states,
        order=order,
        active_player=active_player,
        phase=phase,
        setup_queue=setup_queue,
        faction_queue=faction_queue,
        bonus_available=bonus_available,
        passed=frozenset(),
        pass_order=(),
        round=1,
        scoring=scoring,
        cult_spades=(0,) * n,
        used_power_actions=frozenset(),
        used_orders={},
        town_tiles=(2, 2, 2, 2, 2) + ((1, 1, 1) if config.promo_town_tiles else ()),
    )
    events = [
        Event(
            "game_started",
            f"Terra Mystica: {n} players, {seat_label(order[0])} starts.",
            {
                "num_players": n,
                "starting_player": order[0],
            },
        ),
        Event(
            "scoring_tiles",
            "Round scoring: "
            + ", ".join(
                f"{tile.action.value} ({bonus_text(tile.bonus)})" for tile in scoring
            )
            + ".",
            {
                "scoring": [tile.action.value for tile in scoring],
                "bonuses": [cult_bonus_json(tile.bonus) for tile in scoring],
            },
        ),
    ]
    if phase == "faction_choice":
        events.append(
            Event(
                "faction_choice",
                f"{seat_label(active_player)} chooses a faction.",
                {"player": active_player},
            )
        )
    else:
        events.append(
            Event(
                "factions",
                "; ".join(
                    f"{seat_label(PlayerId(seat))} plays {player.faction.value}"
                    for seat, player in enumerate(player_states)
                ),
                {
                    "factions": [
                        {"player": seat, "faction": player.faction.value}
                        for seat, player in enumerate(player_states)
                    ]
                },
            )
        )
        events.append(
            Event(
                "setup_dwelling",
                f"{seat_label(setup_queue[0])} places a starting dwelling.",
                {"player": setup_queue[0]},
            )
        )
    return Transition(state, tuple(events))


def choose_faction(
    state: TerraMysticaState, player: PlayerId, faction: FactionType
) -> Transition[TerraMysticaState]:
    """Choose an unused faction, then start the dwelling setup."""
    if state.phase != "faction_choice":
        raise IllegalActionError("no faction is being chosen now")
    if player != state.active_player:
        raise IllegalActionError(f"it is {seat_label(state.active_player)}'s turn")
    chosen = {
        state.players[seat].faction
        for seat in range(len(state.players))
        if seat not in state.faction_queue
    }
    terrains = {
        state.players[seat].home_terrain
        for seat in range(len(state.players))
        if seat not in state.faction_queue
    }
    if faction in chosen or FACTION_BY_TYPE[faction].home_terrain in terrains:
        raise IllegalActionError("that colour was already chosen")
    state = replace_player(state, player, _player_state(state.config, faction))
    queue = state.faction_queue[1:]
    events = [
        Event(
            "faction_chosen",
            f"{seat_label(player)} chose {faction.value}.",
            {"player": player, "faction": faction.value},
        )
    ]
    if queue:
        state = replace(state, faction_queue=queue, active_player=queue[0])
        events.append(
            Event(
                "faction_choice",
                f"{seat_label(queue[0])} chooses a faction.",
                {"player": queue[0]},
            )
        )
        return Transition(state, tuple(events))
    state = replace(state, faction_queue=(), phase="setup")
    return _begin_dwellings(state, tuple(events))


def _begin_dwellings(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    setup_queue = initial_setup_queue(state.order, state.players)
    state = replace(
        state,
        phase="setup",
        setup_queue=setup_queue,
        active_player=setup_queue[0],
    )
    return Transition(
        state,
        (
            *events,
            Event(
                "setup_dwelling",
                f"{seat_label(setup_queue[0])} places a starting dwelling.",
                {"player": setup_queue[0]},
            ),
        ),
    )


def place_starting_dwelling(
    state: TerraMysticaState, player: PlayerId, position: Hex
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    tile = state.board.tile(position)
    if tile is None:
        raise IllegalActionError("there is no tile there")
    if not tile.is_land:
        raise IllegalActionError("you cannot build on a river")
    if tile.terrain is not owner.home_terrain:
        raise IllegalActionError("starting dwellings must be on home terrain")
    if tile.building is not None:
        raise IllegalActionError("that tile is occupied")
    board = state.board.place(position, Building(BuildingType.DWELLING, player))
    queue = state.setup_queue[1:]
    events = [
        Event(
            "dwelling_placed",
            f"{seat_label(player)} placed a starting dwelling at "
            f"{position.notation()}.",
            {"player": player, "position": position.notation()},
        )
    ]
    if queue:
        state = replace(
            state,
            board=board,
            setup_queue=queue,
            active_player=queue[0],
        )
        events.append(
            Event(
                "setup_dwelling",
                f"{seat_label(queue[0])} places a starting dwelling.",
                {"player": queue[0]},
            )
        )
        return Transition(state, tuple(events))
    state = replace(state, board=board, setup_queue=())
    if state.config.bonus_cards:
        return begin_bonus_draft(state, tuple(events))
    state, round_events = start_round(state)
    return Transition(state, (*events, *round_events))


def setup_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    if state.phase == "faction_choice":
        terrains = {
            state.players[seat].home_terrain
            for seat in range(len(state.players))
            if seat not in state.faction_queue
        }
        return [
            ChooseFaction(profile.type)
            for profile in FACTION_BY_TYPE.values()
            if profile.home_terrain not in terrains
        ]
    owner = state.players[player]
    return [
        BuildDwelling(tile.position)
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is owner.home_terrain and tile.building is None
    ]


def explain_setup(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    if state.phase == "faction_choice":
        if not isinstance(action, ChooseFaction):
            return "Choose a faction."
        terrains = {
            state.players[seat].home_terrain
            for seat in range(len(state.players))
            if seat not in state.faction_queue
        }
        if FACTION_BY_TYPE[action.faction].home_terrain in terrains:
            return "That colour was already chosen."
        return "Choose an unused colour."
    if isinstance(action, BuildDwelling):
        tile = state.board.tile(action.position)
        if tile is None:
            return "There is no tile there."
        if not tile.is_land:
            return "You cannot build on a river."
        if tile.building is not None:
            return "That tile is occupied."
        if tile.terrain is not state.players[player].home_terrain:
            return "Starting dwellings must be on your home terrain."
    return "Place a starting dwelling on a free home-terrain tile."
