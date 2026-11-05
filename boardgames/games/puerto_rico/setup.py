"""Puerto Rico setup: config checks and the opening table for a seed."""

from boardgames.core import (
    ConfigError,
    Event,
    PlayerId,
    Rng,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import (
    BUILDINGS,
    COLONIST_SUPPLY,
    GOOD_SUPPLY,
    PLANTATION_TILES,
    QUARRY_SUPPLY,
    ROLES_BY_PLAYERS,
    SHIP_CAPACITIES,
    STARTING_DOUBLOONS,
    VICTORY_POINT_SUPPLY,
    Good,
)
from boardgames.games.puerto_rico.model import (
    CargoShip,
    Plantation,
    PlayerState,
    PuertoRicoConfig,
    PuertoRicoState,
    RoleState,
)


def check_config(config: PuertoRicoConfig) -> None:
    """Raise ConfigError for an unplayable table or supply."""
    if not 3 <= config.num_players <= 5:
        raise ConfigError(
            f"Puerto Rico needs 3, 4 or 5 players, got {config.num_players}"
        )
    if config.victory_point_supply < 0:
        raise ConfigError(
            "victory_point_supply must be 0 (standard) or positive, got "
            f"{config.victory_point_supply}"
        )
    if config.max_rounds < 0:
        raise ConfigError(f"max_rounds must be 0 or positive, got {config.max_rounds}")
    return


def starting_plantations(num_players: int) -> tuple[Good, ...]:
    """Starting tile per order position: indigo first, then corn."""
    indigo_count = num_players - (1 if num_players == 3 else 2)
    return tuple(
        "indigo" if index < indigo_count else "corn" for index in range(num_players)
    )


def start_game(config: PuertoRicoConfig, seed: int) -> Transition[PuertoRicoState]:
    """Seat the governor, deal the plantations and fill every supply for `seed`."""
    rng = Rng.seeded(seed)
    n = config.num_players
    governor_index, rng = rng.below(n)
    order = tuple(PlayerId((governor_index + i) % n) for i in range(n))
    governor = order[0]
    roles = tuple(RoleState(role) for role in ROLES_BY_PLAYERS[n])
    starting = starting_plantations(n)
    players_list: list[PlayerState | None] = [None] * n
    for order_index, seat in enumerate(order):
        players_list[seat] = PlayerState(
            doubloons=STARTING_DOUBLOONS[n],
            plantations=(Plantation(starting[order_index]),),
        )
    players = tuple(player for player in players_list if player is not None)
    deck_counts = dict(PLANTATION_TILES)
    for good in starting:
        deck_counts[good] -= 1
    deck_list = [good for good, count in deck_counts.items() for _ in range(count)]
    shuffled, rng = rng.shuffled(deck_list)
    face_up_count = n + 1
    face_up = tuple(shuffled[:face_up_count])
    plantation_deck = tuple(shuffled[face_up_count:])
    available = tuple(
        name for name, spec in BUILDINGS.items() for _ in range(spec.copies)
    )
    ships = tuple(CargoShip(capacity) for capacity in SHIP_CAPACITIES[n])
    vp_supply = (
        config.victory_point_supply
        if config.victory_point_supply > 0
        else VICTORY_POINT_SUPPLY[n]
    )
    state = PuertoRicoState(
        config=config,
        rng=rng,
        round=1,
        governor=governor,
        order=order,
        phase="role_selection",
        active_role=None,
        active_player=governor,
        roles=roles,
        players=players,
        colonist_ship=n,
        colonist_supply=COLONIST_SUPPLY[n],
        trading_house=(),
        cargo_ships=ships,
        face_up=face_up,
        plantation_deck=plantation_deck,
        plantation_discard=(),
        available_buildings=available,
        quarry_supply=QUARRY_SUPPLY,
        goods_supply=GOOD_SUPPLY,
        vp_supply=vp_supply,
        players_acted=frozenset(),
        captain_passes=0,
        colonist_shortage=False,
        end_reason=None,
        winner=None,
    )
    events = (
        Event(
            "game_started",
            f"Puerto Rico: {n} players, {seat_label(governor)} is governor.",
            {"num_players": n, "governor": governor},
        ),
        Event(
            "role_selection",
            f"{seat_label(governor)} chooses the first role.",
            {"player": governor},
        ),
    )
    return Transition(state, events)
