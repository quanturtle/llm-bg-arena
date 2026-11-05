"""Terra Mystica setup: the config check, the opening state and starting dwellings."""

from dataclasses import replace

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
    FACTION_BY_TYPE,
    FACTIONS_BY_TERRAIN,
    SCORING_TILES,
    TERRAIN_WHEEL,
    BuildingType,
    FactionType,
    ScoringAction,
)
from boardgames.games.terra_mystica.model import (
    Action,
    Board,
    BuildDwelling,
    Building,
    Hex,
    PlayerState,
    TerraMysticaConfig,
    TerraMysticaState,
    cult_bonus_json,
)
from boardgames.games.terra_mystica.rounds import bonus_text, start_round


def check_config(config: TerraMysticaConfig) -> None:
    if not 2 <= config.num_players <= 5:
        raise ConfigError(
            f"Terra Mystica needs 2 to 5 players, got {config.num_players}"
        )
    if not 1 <= config.rounds <= 6:
        raise ConfigError(f"rounds must be from 1 to 6, got {config.rounds}")
    return


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


def start_game(config: TerraMysticaConfig, seed: int) -> Transition[TerraMysticaState]:
    rng = Rng.seeded(seed)
    n = config.num_players
    first_seat, rng = rng.below(n)
    order: tuple[PlayerId, ...] = tuple(
        PlayerId((first_seat + offset) % n) for offset in range(n)
    )
    terrains, rng = rng.shuffled(TERRAIN_WHEEL)
    factions: list[FactionType] = []
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

    profiles = [FACTION_BY_TYPE[faction] for faction in factions]
    player_states = tuple(
        PlayerState(
            faction=profile.type,
            resources=profile.starting_resources,
            victory_points=20,
            cults=profile.starting_cults,
            shipping=profile.shipping_start,
            digging=profile.digging_start,
        )
        for profile in profiles
    )

    setup_queue = initial_setup_queue(order, player_states)
    state = TerraMysticaState(
        config=config,
        rng=rng,
        board=Board.base(),
        players=player_states,
        order=order,
        active_player=setup_queue[0],
        phase="setup",
        setup_queue=setup_queue,
        passed=frozenset(),
        pass_order=(),
        round=1,
        scoring=scoring,
        cult_spades=(0,) * n,
        used_power_actions=frozenset(),
        used_orders={},
    )
    events = (
        Event(
            "game_started",
            f"Terra Mystica: {n} players, {seat_label(order[0])} starts.",
            {"num_players": n, "starting_player": order[0]},
        ),
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
        Event(
            "setup_dwelling",
            f"{seat_label(setup_queue[0])} places a starting dwelling.",
            {"player": setup_queue[0]},
        ),
    )
    return Transition(state, events)


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
    state, round_events = start_round(state)
    return Transition(state, (*events, *round_events))


def setup_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    return [
        BuildDwelling(tile.position)
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is owner.home_terrain and tile.building is None
    ]


def explain_setup(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
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
