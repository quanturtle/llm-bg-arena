"""Unit tests for the Puerto Rico game implementation.

The tests below check the standard base-game rules: setup, every role, the
end-game bonuses, the observation privacy, determinism and random play.
"""

import asyncio
from dataclasses import replace

import pytest

from boardgames.arena.runner import play_match
from boardgames.core import (
    ConfigError,
    IllegalActionError,
    NotationError,
    PlayerId,
    create_game,
    seats,
)
from boardgames.games.puerto_rico import (
    Action,
    Build,
    DiscardGoods,
    FinishPlacement,
    LoadShip,
    LoadWharf,
    Pass,
    PickUpColonist,
    PlaceColonist,
    ProducePrivilege,
    PuertoRico,
    PuertoRicoConfig,
    PuertoRicoState,
    SelectRole,
    Sell,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
)
from boardgames.games.puerto_rico.constants import (
    COLONIST_SUPPLY,
    GOOD_SUPPLY,
    PLANTATION_TILES,
    ROLES_BY_PLAYERS,
    SHIP_CAPACITIES,
    STARTING_DOUBLOONS,
    Role,
)
from boardgames.games.puerto_rico.game import discard_actions
from boardgames.games.puerto_rico.model import (
    CargoShip,
    OwnedBuilding,
    Plantation,
    PlayerState,
    RoleState,
    available_to_build,
    build_cost,
    building_points,
    can_ship,
    city_spaces_used,
    end_game_bonus,
    factory_bonus_for_produced,
    goods_from,
    goods_get,
    goods_total,
    production,
    public_points,
    replace_player,
    replace_role,
    role_chooser,
    role_state,
    sell_price,
    ship_victory_points,
    total_points,
)
from boardgames.games.puerto_rico.roles.craftsman import (
    craftsman_actions,
    run_production,
)
from boardgames.games.puerto_rico.rounds import (
    check_end_game,
    compute_winner,
    end_round,
    finish_standard_phase,
    refill_colonist_ship,
    tiebreak_key,
)
from boardgames.logs.replay import replay_match
from boardgames.logs.schema import LogRecord
from tests.arena.support import FakeClock, MemorySink, random_agents
from tests.invariants.playthrough import random_playthrough

GAME = PuertoRico()
P1, P2, P3 = seats(3)


def start(num_players: int = 3, seed: int = 7, **config: int) -> PuertoRicoState:
    return GAME.setup(PuertoRicoConfig(num_players=num_players, **config), seed).state


def notations(state: PuertoRicoState) -> list[str]:
    (decision,) = GAME.pending_decisions(state)
    listing = GAME.legal_actions(state, decision).listing(10_000)
    assert listing is not None
    return [GAME.format_action(action) for action in listing]


def play(state: PuertoRicoState, notation: str) -> PuertoRicoState:
    (decision,) = GAME.pending_decisions(state)
    action = GAME.parse_action(notation)
    return GAME.apply(state, decision.player, action).state


def select_role(state: PuertoRicoState, role: Role) -> PuertoRicoState:
    (decision,) = GAME.pending_decisions(state)
    return GAME.apply(state, decision.player, SelectRole(role)).state


def drain(state: PuertoRicoState) -> PuertoRicoState:
    """Play the current phase to its end, passing or finishing when possible."""
    while state.phase not in ("role_selection", "game_over"):
        options = notations(state)
        if "pass" in options:
            choice = "pass"
        elif "finish" in options:
            choice = "finish"
        elif "discard none" in options:
            choice = "discard none"
        else:
            choice = options[0]
        state = play(state, choice)
    return state


def with_doubloons(
    state: PuertoRicoState, player: PlayerId, amount: int
) -> PuertoRicoState:
    return replace_player(
        state, player, replace(state.players[player], doubloons=amount)
    )


def with_goods(
    state: PuertoRicoState, player: PlayerId, **counts: int
) -> PuertoRicoState:
    return replace_player(
        state, player, replace(state.players[player], goods=goods_from(**counts))
    )


def with_vp_chips(
    state: PuertoRicoState, player: PlayerId, amount: int
) -> PuertoRicoState:
    return replace_player(
        state, player, replace(state.players[player], vp_chips=amount)
    )


def with_buildings(
    state: PuertoRicoState,
    player: PlayerId,
    *buildings: OwnedBuilding,
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(state.players[player], buildings=buildings),
    )


def with_plantations(
    state: PuertoRicoState,
    player: PlayerId,
    *plantations: Plantation,
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(state.players[player], plantations=plantations),
    )


def with_quarries(
    state: PuertoRicoState,
    player: PlayerId,
    quarries: int,
    occupied: int = 0,
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(
            state.players[player],
            quarries=quarries,
            occupied_quarries=occupied,
        ),
    )


def with_colonists(
    state: PuertoRicoState, player: PlayerId, amount: int
) -> PuertoRicoState:
    return replace_player(
        state,
        player,
        replace(state.players[player], colonists_unplaced=amount),
    )


def with_role(state: PuertoRicoState, role: Role, player: PlayerId) -> PuertoRicoState:
    entry = role_state(state, role)
    return replace_role(
        state, role, RoleState(role=role, doubloons=entry.doubloons, taken_by=player)
    )


def total_goods_on_board(state: PuertoRicoState) -> int:
    """Goods in the bank, hands, ships and trading house; must never change."""
    return (
        sum(state.goods_supply)
        + sum(goods_total(player.goods) for player in state.players)
        + sum(ship.filled for ship in state.cargo_ships)
        + len(state.trading_house)
    )


def total_colonists(state: PuertoRicoState) -> int:
    """Colonists in the bank, ship, island, city and San Juan."""
    return (
        state.colonist_supply
        + state.colonist_ship
        + sum(
            player.colonists_unplaced
            + sum(1 for plantation in player.plantations if plantation.colonized)
            + player.occupied_quarries
            + sum(building.colonists for building in player.buildings)
            for player in state.players
        )
    )


# Setup --------------------------------------------------------------------


def test_initial_state_has_governor_and_role_selection() -> None:
    state = start(seed=7)
    assert state.phase == "role_selection"
    assert state.active_role is None
    assert state.order[0] == state.governor
    assert state.active_player == state.governor


def test_setup_for_three_players() -> None:
    state = start(num_players=3, seed=7)
    assert len(state.players) == 3
    assert all(player.doubloons == STARTING_DOUBLOONS[3] for player in state.players)
    assert len(state.roles) == 6 == len(ROLES_BY_PLAYERS[3])
    assert "prospector" not in {role.role for role in state.roles}
    assert len(state.face_up) == 4
    assert len(state.plantation_deck) == (sum(PLANTATION_TILES.values()) - 3 - 4)
    assert state.colonist_ship == 3
    assert state.colonist_supply == COLONIST_SUPPLY[3]
    assert state.vp_supply == 75
    assert state.trading_house == ()
    assert state.quarry_supply == 8
    assert state.goods_supply == GOOD_SUPPLY
    assert tuple(ship.capacity for ship in state.cargo_ships) == SHIP_CAPACITIES[3]
    indigo_count = 2
    for order_index, seat in enumerate(state.order):
        plantation = state.players[seat].plantations[0]
        assert plantation.good == ("indigo" if order_index < indigo_count else "corn")
        assert not plantation.colonized


@pytest.mark.parametrize(
    ("num_players", "role_count", "indigo_count"),
    [(4, 7, 2), (5, 8, 3)],
)
def test_setup_for_four_and_five_players(
    num_players: int, role_count: int, indigo_count: int
) -> None:
    state = start(num_players=num_players, seed=11)
    assert len(state.roles) == role_count == len(ROLES_BY_PLAYERS[num_players])
    role_names = {role.role for role in state.roles}
    assert "prospector" in role_names
    assert ("prospector_2" in role_names) is (num_players == 5)
    assert all(
        player.doubloons == STARTING_DOUBLOONS[num_players] for player in state.players
    )
    assert state.colonist_supply == COLONIST_SUPPLY[num_players]
    assert state.vp_supply == {4: 100, 5: 122}[num_players]
    assert len(state.face_up) == num_players + 1
    for order_index, seat in enumerate(state.order):
        good = state.players[seat].plantations[0].good
        assert good == ("indigo" if order_index < indigo_count else "corn")


def test_setup_is_deterministic_per_seed() -> None:
    assert start(seed=9) == start(seed=9)
    assert GAME.setup(PuertoRicoConfig(num_players=3), 9).events == (
        GAME.setup(PuertoRicoConfig(num_players=3), 9).events
    )
    assert start(seed=9) != start(seed=10)


def test_config_validation_and_registry() -> None:
    assert GAME.parse_config({}) == PuertoRicoConfig()
    config = PuertoRicoConfig(num_players=5, victory_point_supply=50, max_rounds=10)
    assert GAME.parse_config(GAME.config_json(config)) == config
    for raw in (
        {"num_players": 2},
        {"num_players": 6},
        {"victory_point_supply": -1},
        {"max_rounds": -1},
    ):
        with pytest.raises(ConfigError):
            GAME.parse_config(raw)
    assert isinstance(create_game("puerto_rico"), PuertoRico)


# Notation -----------------------------------------------------------------


def test_notation_round_trips_every_action() -> None:
    actions: list[Action] = [
        SelectRole("settler"),
        SelectRole("prospector"),
        TakePlantation("corn"),
        TakePlantation("corn", use_hospice=False),
        TakeQuarry(),
        TakeQuarry(use_hospice=False),
        UseHacienda(),
        Pass(),
        Build("small_indigo_plant"),
        Build("small_indigo_plant", use_university=False),
        ProducePrivilege("coffee"),
        Sell("tobacco"),
        LoadShip("indigo", 0),
        LoadShip("coffee", 2),
        LoadWharf("sugar"),
        PlaceColonist("plantation", 0),
        PlaceColonist("building", 2),
        PlaceColonist("quarry"),
        PickUpColonist("plantation", 1),
        PickUpColonist("building", 0),
        PickUpColonist("quarry"),
        FinishPlacement(),
        DiscardGoods(),
        DiscardGoods(("corn", "indigo")),
        DiscardGoods(("corn",), "indigo"),
    ]
    for action in actions:
        assert GAME.parse_action(GAME.format_action(action)) == action


@pytest.mark.parametrize(
    "text",
    [
        "role",
        "role alien",
        "take",
        "take mango",
        "build",
        "build castle",
        "privilege",
        "privilege mango",
        "sell",
        "sell mango",
        "ship corn 1",
        "ship corn s0",
        "ship corn s4",
        "wharf corn s1",
        "place plantation",
        "place building -1",
        "place quarry 0",
        "pick building x",
        "discard mango",
        "discard ",
        "discard  indigo",
        "discard\tindigo",
        "finish ",
    ],
)
def test_parse_rejects_non_canonical_text(text: str) -> None:
    with pytest.raises(NotationError):
        GAME.parse_action(text)


def test_discard_notation_is_canonical() -> None:
    for text in (
        "discard none",
        "discard corn none",
        "discard keep indigo",
        "discard corn keep indigo",
    ):
        assert GAME.format_action(GAME.parse_action(text)) == text
    for text in (
        "discard",
        "discard corn",
        "discard keep corn none",
        "discard none keep corn",
    ):
        with pytest.raises(NotationError):
            GAME.parse_action(text)


def test_off_board_indices_parse_but_are_illegal() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 1)
    action = GAME.parse_action("place plantation 999")
    assert GAME.format_action(action) == "place plantation 999"
    with pytest.raises(IllegalActionError):
        GAME.apply(state, player, action)


# Production and bonuses ---------------------------------------------------


def test_production_uses_matching_plantations_and_buildings() -> None:
    player = PlayerState(
        plantations=(
            Plantation("corn", True),
            Plantation("indigo", True),
            Plantation("indigo", True),
            Plantation("sugar", True),
            Plantation("sugar", True),
            Plantation("tobacco", True),
            Plantation("coffee", True),
            Plantation("corn", False),
        ),
        buildings=(
            OwnedBuilding("small_indigo_plant", 1),
            OwnedBuilding("indigo_plant", 3),
            OwnedBuilding("small_sugar_mill", 1),
            OwnedBuilding("sugar_mill", 3),
            OwnedBuilding("tobacco_storage", 3),
            OwnedBuilding("coffee_roaster", 2),
        ),
    )
    assert production(player) == goods_from(
        corn=1, indigo=2, sugar=2, tobacco=1, coffee=1
    )


def test_production_is_limited_by_colonists() -> None:
    player = PlayerState(
        plantations=(Plantation("indigo", True), Plantation("indigo", True)),
        buildings=(OwnedBuilding("indigo_plant", 0),),
    )
    assert production(player) == goods_from()
    player = replace(player, buildings=(OwnedBuilding("indigo_plant", 1),))
    assert production(player) == goods_from(indigo=1)


def test_factory_bonus_counts_distinct_goods() -> None:
    player = PlayerState(
        plantations=(
            Plantation("corn", True),
            Plantation("indigo", True),
            Plantation("sugar", True),
        ),
        buildings=(
            OwnedBuilding("factory", 1),
            OwnedBuilding("small_indigo_plant", 1),
            OwnedBuilding("small_sugar_mill", 1),
        ),
    )
    assert factory_bonus_for_produced(player, production(player)) == 2  # three types
    player = replace(
        player,
        plantations=(Plantation("corn", True), Plantation("indigo", True)),
    )
    assert factory_bonus_for_produced(player, production(player)) == 1  # two types
    player = replace(player, plantations=(Plantation("corn", True),))
    assert factory_bonus_for_produced(player, production(player)) == 0
    player = replace(player, buildings=())
    assert factory_bonus_for_produced(player, production(player)) == 0


def test_market_and_trader_bonuses_set_sale_price() -> None:
    state = start(seed=2)
    player = state.order[0]
    assert sell_price(state, player, "indigo") == 1
    state = with_role(state, "trader", player)
    assert sell_price(state, player, "indigo") == 2
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            buildings=(OwnedBuilding("small_market", 1),),
        ),
    )
    assert sell_price(state, player, "indigo") == 3
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            buildings=(
                OwnedBuilding("small_market", 1),
                OwnedBuilding("large_market", 1),
            ),
        ),
    )
    assert sell_price(state, player, "indigo") == 5
    assert sell_price(state, player, "corn") == 4


def test_build_cost_uses_quarries_and_builder_privilege() -> None:
    state = start(seed=2)
    player = state.order[0]
    state = with_quarries(state, player, quarries=2, occupied=2)
    assert build_cost(state, player, "indigo_plant") == 1
    assert build_cost(state, player, "small_market") == 0
    assert build_cost(state, player, "sugar_mill") == 2
    state = with_role(state, "builder", player)
    assert build_cost(state, player, "indigo_plant") == 0
    assert build_cost(state, player, "sugar_mill") == 1
    assert build_cost(state, player, "tobacco_storage") == 2


def test_available_to_build_reports_each_type_once() -> None:
    state = start(seed=2)
    player = state.order[0]
    state = with_doubloons(state, player, 20)
    choices = available_to_build(state, player)
    assert len(choices) == len(set(choices))
    assert "small_indigo_plant" in choices
    state = with_quarries(state, player, quarries=6, occupied=6)
    assert build_cost(state, player, "city_hall") == 6


# End-game scoring ---------------------------------------------------------


def test_building_points_are_the_printed_values() -> None:
    player = PlayerState(
        buildings=(
            OwnedBuilding("small_indigo_plant", 0),
            OwnedBuilding("indigo_plant", 3),
            OwnedBuilding("tobacco_storage", 0),
            OwnedBuilding("city_hall", 1),
        )
    )
    assert building_points(player) == 1 + 2 + 3 + 4


def test_guild_hall_bonus_for_production_buildings() -> None:
    player = PlayerState(
        buildings=(
            OwnedBuilding("guild_hall", 1),
            OwnedBuilding("small_indigo_plant", 1),
            OwnedBuilding("indigo_plant", 1),
            OwnedBuilding("tobacco_storage", 1),
        )
    )
    assert end_game_bonus(player) == 1 + 2 + 2


def test_residence_bonus_for_placed_island_tiles() -> None:
    player = PlayerState(
        plantations=tuple(Plantation("corn", True) for _ in range(12)),
        buildings=(OwnedBuilding("residence", 1),),
    )
    assert end_game_bonus(player) == 7
    player = replace(
        player,
        plantations=tuple(Plantation("corn", True) for _ in range(9)),
    )
    assert end_game_bonus(player) == 4
    player = replace(
        player,
        plantations=(Plantation("corn", True), Plantation("corn", True)),
        quarries=2,
        occupied_quarries=2,
    )
    assert end_game_bonus(player) == 4


def test_fortress_bonus_counts_colonists_on_the_player_board() -> None:
    player = PlayerState(
        plantations=(Plantation("corn", True), Plantation("indigo", True)),
        quarries=3,
        occupied_quarries=3,
        buildings=(
            OwnedBuilding("fortress", 1),
            OwnedBuilding("indigo_plant", 1),
        ),
        colonists_unplaced=2,
    )
    # 2 plantation colonists + 3 quarry colonists + 2 building colonists
    # + 2 unplaced = 9.
    assert end_game_bonus(player) == 3


def test_customs_house_and_city_hall_bonuses() -> None:
    customs = PlayerState(vp_chips=9, buildings=(OwnedBuilding("customs_house", 1),))
    assert end_game_bonus(customs) == 2
    city = PlayerState(
        buildings=(
            OwnedBuilding("city_hall", 1),
            OwnedBuilding("small_market", 1),
            OwnedBuilding("large_market", 1),
            OwnedBuilding("small_indigo_plant", 1),
        )
    )
    assert end_game_bonus(city) == 3  # city_hall, small_market, large_market


def test_total_points_adds_chips_buildings_and_bonuses() -> None:
    player = PlayerState(
        vp_chips=5,
        buildings=(
            OwnedBuilding("customs_house", 1),
            OwnedBuilding("small_indigo_plant", 1),
        ),
    )
    assert total_points(player) == 5 + 4 + 1 + (5 // 4)


# Roles: Settler -----------------------------------------------------------


@pytest.mark.parametrize("role", ["prospector", "prospector_2"])
def test_prospector_gives_a_doubloon_and_skips_the_action_phase(
    role: Role,
) -> None:
    state = start(num_players=5, seed=7)
    player = state.active_player
    before = state.players[player].doubloons
    state = select_role(state, role)
    assert state.players[player].doubloons == before + 1
    assert state.phase == "role_selection"
    assert role_chooser(state, role) == player


def test_settler_role_takes_a_plantation_and_refreshes_face_up() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = select_role(state, "settler")
    assert state.phase == "settler_action"
    assert state.active_role == "settler"
    assert state.active_player == governor
    options = notations(state)
    assert "take quarry" in options  # the role chooser's privilege
    choice = next(
        option
        for option in options
        if option.startswith("take ") and option != "take quarry"
    )
    good = choice.split()[1]
    state = play(state, choice)
    assert len(state.players[governor].plantations) == 2
    assert state.players[governor].plantations[-1].good == good
    assert not state.players[governor].plantations[-1].colonized
    state = drain(state)
    assert state.phase == "role_selection"
    assert len(state.face_up) == 4
    assert role_chooser(state, "settler") == governor


def test_settler_privilege_can_take_a_quarry() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = select_role(state, "settler")
    before_supply = state.quarry_supply
    state = play(state, "take quarry")
    owner = state.players[governor]
    assert owner.quarries == 1
    assert owner.occupied_quarries == 0
    assert state.quarry_supply == before_supply - 1


def test_construction_hut_lets_another_player_take_a_quarry() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = select_role(state, "settler")
    state = play(state, "pass")
    other = state.active_player
    assert other != governor
    state = with_buildings(state, other, OwnedBuilding("construction_hut", 1))
    assert "take quarry" in notations(state)
    state = play(state, "take quarry")
    assert state.players[other].quarries == 1


def test_hospice_colonizes_a_taken_plantation() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = with_buildings(state, governor, OwnedBuilding("hospice", 1))
    state = select_role(state, "settler")
    before_supply = state.colonist_supply
    options = [
        option
        for option in notations(state)
        if option.startswith("take ") and option != "take quarry"
    ]
    state = play(state, options[0])
    plantation = state.players[governor].plantations[-1]
    assert plantation.colonized
    assert state.colonist_supply == before_supply - 1


def test_hacienda_draws_an_extra_plantation_once() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = with_buildings(state, governor, OwnedBuilding("hacienda", 1))
    state = select_role(state, "settler")
    before_deck = len(state.plantation_deck)
    before_plantations = len(state.players[governor].plantations)
    state = play(state, "hacienda")
    assert len(state.plantation_deck) == before_deck - 1
    assert len(state.players[governor].plantations) == before_plantations + 1
    assert state.players[governor].hacienda_used
    assert "hacienda" not in notations(state)


def test_hacienda_can_draw_when_only_the_discard_pile_remains() -> None:
    state = start(seed=3)
    governor = state.order[0]
    state = with_buildings(state, governor, OwnedBuilding("hacienda", 1))
    state = replace(
        state,
        plantation_deck=(),
        plantation_discard=("coffee", "coffee"),
    )
    state = select_role(state, "settler")
    assert "hacienda" in notations(state)
    state = play(state, "hacienda")
    owner = state.players[governor]
    assert owner.plantations[-1].good == "coffee"
    assert state.plantation_discard == ()
    assert state.plantation_deck == ("coffee",)


def test_settler_draws_leftover_deck_before_reshuffling_discards() -> None:
    state = start(seed=3)
    state = replace(
        state,
        active_role="settler",
        face_up=(),
        plantation_deck=("coffee",),
        plantation_discard=("corn", "corn", "corn"),
    )
    state = finish_standard_phase(state)[0]
    assert state.face_up[0] == "coffee"
    assert state.face_up[1:] == ("corn", "corn", "corn")


def test_settler_keeps_unchosen_plantations_in_a_discard_pile() -> None:
    state = start(seed=3)
    state = select_role(state, "settler")
    taken = state.face_up[0]
    unchosen = state.face_up[1:]
    state = play(state, f"take {taken}")
    while state.phase == "settler_action":
        state = play(state, "pass")
    assert state.plantation_discard == unchosen
    assert len(state.face_up) == 4


# Roles: Mayor -------------------------------------------------------------


def test_short_colonist_refill_is_announced_and_observed() -> None:
    state = replace(
        start(seed=5),
        active_role="mayor",
        phase="mayor_action",
        colonist_supply=0,
        colonist_ship=0,
    )
    state, events = finish_standard_phase(state)
    assert state.colonist_shortage
    assert any(event.kind == "colonist_shortage" for event in events)
    observation = GAME.observe(state, None)
    assert observation.data["colonist_shortage"] is True


def test_mayor_event_omits_the_extra_colonist_when_the_supply_is_empty() -> None:
    state = replace(start(seed=5), colonist_supply=0, colonist_ship=3)
    player = state.active_player
    transition = GAME.apply(state, player, SelectRole("mayor"))
    event = next(
        event for event in transition.events if event.kind == "colonists_distributed"
    )
    assert "no extra colonist" in event.text
    assert "takes the extra colonist" not in event.text


def test_mayor_distributes_colonists_and_refills_the_ship() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    assert state.phase == "mayor_action"
    assert state.colonist_ship == 0
    chooser = state.active_player
    assert state.players[chooser].colonists_unplaced >= 2
    state = drain(state)
    assert state.phase == "role_selection"
    assert state.colonist_ship == 3
    assert role_chooser(state, "mayor") == chooser


def test_mayor_place_and_pick_up_colonists() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 1)
    # Place on the starting plantation, then pick it back up.
    state = play(state, "place plantation 0")
    assert state.players[player].plantations[0].colonized
    assert state.players[player].colonists_unplaced == 0
    assert "pick plantation 0" in notations(state)
    state = play(state, "pick plantation 0")
    assert not state.players[player].plantations[0].colonized
    assert state.players[player].colonists_unplaced == 1


def test_mayor_closes_when_no_placement_targets_remain() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 0)
    state = with_plantations(state, player, Plantation("corn", True))
    assert "finish" in notations(state)


def test_mayor_places_new_colonists_before_moving_existing_ones() -> None:
    state = start(seed=5)
    state = select_role(state, "mayor")
    player = state.active_player
    state = with_colonists(state, player, 2)
    state = with_plantations(
        state,
        player,
        Plantation("corn", True),
        Plantation("indigo", False),
        Plantation("sugar", False),
    )
    assert not any(option.startswith("pick ") for option in notations(state))
    state = play(state, "place plantation 1")
    state = play(state, "place plantation 2")
    assert state.players[player].colonists_unplaced == 0
    assert "pick plantation 0" in notations(state)


# Roles: Builder -----------------------------------------------------------


def test_builder_builds_with_privilege_discount() -> None:
    state = start(seed=6)
    chooser = state.order[0]
    state = with_doubloons(state, chooser, 10)
    state = select_role(state, "builder")
    assert state.phase == "builder_action"
    assert "build small_indigo_plant" in notations(state)
    state = play(state, "build small_indigo_plant")
    owner = state.players[chooser]
    assert owner.owns("small_indigo_plant")
    assert owner.doubloons == 10  # cost 1 minus the Builder's doubloon
    assert state.available_buildings.count("small_indigo_plant") == 3
    state = drain(state)
    assert state.phase == "role_selection"


def test_builder_quarry_discount_and_university() -> None:
    state = start(seed=6)
    chooser = state.order[0]
    state = with_doubloons(state, chooser, 10)
    state = with_quarries(state, chooser, quarries=2, occupied=2)
    state = with_buildings(state, chooser, OwnedBuilding("university", 1))
    before_supply = state.colonist_supply
    state = select_role(state, "builder")
    state = play(state, "build sugar_mill")
    owner = state.players[chooser]
    assert owner.owns("sugar_mill")
    assert owner.doubloons == 9  # 4 - 2 quarries - 1 Builder discount
    new_building = owner.buildings[-1]
    assert new_building.name == "sugar_mill"
    assert new_building.colonists == 1
    assert state.colonist_supply == before_supply - 1


# Roles: Craftsman ---------------------------------------------------------


def test_craftsman_produces_for_everyone_and_gives_a_privilege() -> None:
    state = start(seed=8)
    chooser = state.order[0]
    state = with_plantations(
        state,
        chooser,
        Plantation("corn", True),
        Plantation("indigo", True),
    )
    state = with_buildings(state, chooser, OwnedBuilding("small_indigo_plant", 1))
    state = select_role(state, "craftsman")
    assert state.phase == "craftsman_action"
    assert state.active_player == chooser
    assert goods_get(state.players[chooser].goods, "corn") == 1
    assert goods_get(state.players[chooser].goods, "indigo") == 1
    options = notations(state)
    assert "privilege corn" in options
    state = play(state, "privilege corn")
    assert goods_get(state.players[chooser].goods, "corn") == 2
    state = drain(state)
    assert state.phase == "role_selection"


def test_craftsman_factory_bonus() -> None:
    state = start(seed=8)
    chooser = state.order[0]
    state = with_plantations(
        state,
        chooser,
        Plantation("corn", True),
        Plantation("indigo", True),
        Plantation("sugar", True),
    )
    state = with_buildings(
        state,
        chooser,
        OwnedBuilding("factory", 1),
        OwnedBuilding("small_indigo_plant", 1),
        OwnedBuilding("small_sugar_mill", 1),
    )
    before = state.players[chooser].doubloons
    state = select_role(state, "craftsman")
    assert state.players[chooser].doubloons == before + 2


# Roles: Trader ------------------------------------------------------------


def test_trader_sells_a_good_and_keeps_the_house_unless_full() -> None:
    state = start(seed=10)
    chooser = state.order[0]
    state = with_goods(state, chooser, indigo=1, sugar=2)
    state = select_role(state, "trader")
    assert state.phase == "trader_action"
    before = state.players[chooser].doubloons
    assert "sell indigo" in notations(state)
    state = play(state, "sell indigo")
    assert state.players[chooser].doubloons == before + 2
    assert state.trading_house == ("indigo",)
    state = drain(state)
    assert state.phase == "role_selection"
    assert state.trading_house == ("indigo",)


def test_full_trading_house_is_cleared_at_phase_end() -> None:
    state = start(seed=10)
    before = list(state.goods_supply)
    state = replace(
        state,
        active_role="trader",
        phase="trader_action",
        trading_house=("indigo", "sugar", "corn", "coffee"),
    )
    state = finish_standard_phase(state)[0]
    assert state.trading_house == ()
    expected = list(before)
    expected[0] += 1  # corn
    expected[1] += 1  # indigo
    expected[2] += 1  # sugar
    expected[4] += 1  # coffee
    assert list(state.goods_supply) == expected


def test_office_allows_selling_a_duplicate_good() -> None:
    state = start(seed=10)
    chooser = state.order[0]
    state = with_goods(state, chooser, indigo=1)
    state = select_role(state, "trader")
    state = replace(state, trading_house=("indigo",))
    assert "sell indigo" not in notations(state)
    state = with_buildings(state, chooser, OwnedBuilding("office", 1))
    assert "sell indigo" in notations(state)


# Roles: Captain -----------------------------------------------------------


def test_captain_ships_goods_and_takes_the_first_load_bonus() -> None:
    state = start(seed=9)
    chooser = state.order[0]
    state = with_goods(state, chooser, indigo=3)
    state = select_role(state, "captain")
    assert state.phase == "captain_action"
    assert state.active_player == chooser
    assert "ship indigo s1" in notations(state)
    state = play(state, "ship indigo s1")
    assert state.players[chooser].vp_chips == 4  # 3 goods + 1 Captain
    ship = state.cargo_ships[0]
    assert ship.good == "indigo"
    assert ship.filled == 3
    state = drain(state)
    assert state.phase == "role_selection"
    ship = state.cargo_ships[0]
    assert ship.good == "indigo"
    assert ship.filled == 3


def test_captain_full_ships_are_unloaded_at_phase_end() -> None:
    state = start(seed=9)
    chooser = state.order[0]
    state = with_goods(state, chooser, indigo=4)
    state = select_role(state, "captain")
    state = play(state, "ship indigo s1")
    assert state.cargo_ships[0].full
    before_supply = state.goods_supply
    state = drain(state)
    assert state.phase == "role_selection"
    ship = state.cargo_ships[0]
    assert ship.good is None
    assert ship.filled == 0
    assert (
        goods_get(state.goods_supply, "indigo")
        == goods_get(before_supply, "indigo") + 4
    )


def test_captain_wharf_ships_all_of_one_good() -> None:
    state = start(seed=9)
    chooser = state.order[0]
    state = with_goods(state, chooser, sugar=2)
    state = with_buildings(state, chooser, OwnedBuilding("wharf", 1))
    state = select_role(state, "captain")
    assert "wharf sugar" in notations(state)
    state = play(state, "wharf sugar")
    assert state.players[chooser].vp_chips == 3  # 2 goods + 1 Captain
    assert state.players[chooser].wharf_used
    assert goods_get(state.players[chooser].goods, "sugar") == 0
    assert "wharf sugar" not in notations(state)


def test_captain_may_pass_up_the_wharf_when_only_it_can_load() -> None:
    state = start(seed=9)
    chooser = state.order[0]
    state = with_goods(state, chooser, coffee=1)
    state = with_buildings(state, chooser, OwnedBuilding("wharf", 1))
    state = replace(
        state,
        cargo_ships=(
            CargoShip(4, "indigo", 4),
            CargoShip(5, "sugar", 5),
            CargoShip(6, "tobacco", 6),
        ),
    )
    state = select_role(state, "captain")
    assert "wharf coffee" in notations(state)
    assert "pass" in notations(state)
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(Pass()) == "Load goods on a ship or Wharf, or pass if you cannot."
    )
    state = play(state, "pass")
    assert not state.players[chooser].wharf_used
    assert goods_get(state.players[chooser].goods, "coffee") == 1


def test_captain_harbor_adds_a_point_per_shipment() -> None:
    state = start(seed=9)
    chooser = state.order[0]
    state = with_goods(state, chooser, corn=2)
    state = with_buildings(state, chooser, OwnedBuilding("harbor", 1))
    state = select_role(state, "captain")
    state = play(state, "ship corn s1")
    # 2 corn + 1 Captain first load + 1 Harbor
    assert state.players[chooser].vp_chips == 4


def test_captain_bonus_only_applies_to_the_first_load() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_role(state, "captain", player)
    assert ship_victory_points(state, player, 2) == 3
    state = replace_player(
        state,
        player,
        replace(state.players[player], captain_first_load_done=True),
    )
    assert ship_victory_points(state, player, 2) == 2


def test_captain_must_load_if_possible() -> None:
    state = start(seed=9)
    chooser = state.order[0]
    state = with_goods(state, chooser, corn=1)
    state = select_role(state, "captain")
    assert "pass" not in notations(state)
    state = play(state, "ship corn s1")
    # Now the chooser has no goods; passing is legal.
    while state.active_player != chooser:
        state = play(state, "pass")
    assert "pass" in notations(state)


def test_captain_discard_keeps_one_good_and_warehouse_types() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=2, indigo=2)
    state = with_buildings(state, player, OwnedBuilding("small_warehouse", 1))
    state = with_role(state, "captain", player)
    state = replace(
        state,
        phase="captain_discard",
        active_role="captain",
        active_player=player,
        players_acted=frozenset(state.order[1:]),
    )
    assert "discard indigo keep corn" in notations(state)
    state = play(state, "discard indigo keep corn")
    goods = state.players[player].goods
    assert goods_get(goods, "indigo") == 2
    assert goods_get(goods, "corn") == 1


def test_captain_discard_without_warehouse_keeps_one_good() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=2, indigo=3)
    state = with_role(state, "captain", player)
    state = replace(
        state,
        phase="captain_discard",
        active_role="captain",
        active_player=player,
        players_acted=frozenset(state.order[1:]),
    )
    assert notations(state) == [
        "discard none",
        "discard keep corn",
        "discard keep indigo",
    ]
    state = play(state, "discard keep corn")
    goods = state.players[player].goods
    assert goods_get(goods, "corn") == 1
    assert goods_get(goods, "indigo") == 0


# End game ----------------------------------------------------------------


def test_end_game_when_victory_point_supply_runs_out() -> None:
    state = replace(start(seed=1), vp_supply=0)
    ended = check_end_game(state)
    assert ended.phase == "game_over"
    assert ended.end_reason == "victory point supply exhausted"
    assert ended.winner is not None
    assert GAME.is_terminal(ended)


def test_end_game_only_when_the_mayor_cannot_refill_the_ship() -> None:
    state = replace(start(seed=1), colonist_supply=0, colonist_ship=0)
    assert check_end_game(state).end_reason is None
    ended = check_end_game(refill_colonist_ship(state))
    assert ended.end_reason == "colonist supply exhausted"


def test_exact_colonist_refill_does_not_end_the_game() -> None:
    state = replace(start(seed=1), colonist_supply=3)
    refilled = refill_colonist_ship(state)
    assert refilled.colonist_ship == 3
    assert not refilled.colonist_shortage
    assert check_end_game(refilled).end_reason is None


def test_end_game_when_a_city_is_full() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("guild_hall", 0),
        OwnedBuilding("residence", 0),
        OwnedBuilding("fortress", 0),
        OwnedBuilding("customs_house", 0),
        OwnedBuilding("city_hall", 0),
        OwnedBuilding("small_market", 0),
        OwnedBuilding("small_indigo_plant", 0),
    )
    assert city_spaces_used(state.players[player]) == 12
    ended = check_end_game(state)
    assert ended.end_reason == "a player's city is full"


def test_round_limit_ends_the_game() -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=1)
    state = GAME.setup(config, 4).state
    ended = end_round(state)
    assert ended.round == 2
    assert ended.phase == "game_over"
    assert ended.end_reason == "round limit reached"


def test_scores_match_total_points() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_vp_chips(state, player, 6)
    scores = GAME.scores(state)
    assert scores.points[player] == total_points(state.players[player])


def test_winner_breaks_ties_by_doubloons_and_goods() -> None:
    state = start(seed=1)
    p1, p2 = state.order[0], state.order[1]
    state = with_doubloons(state, p1, 4)
    state = with_doubloons(state, p2, 5)
    assert compute_winner(state) == p2
    state = with_goods(state, p1, corn=2)
    assert compute_winner(state) == p1


def test_final_tie_uses_the_last_rounds_governor() -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=1)
    state = GAME.setup(config, 4).state
    final_governor = state.governor
    ended = end_round(state)
    assert ended.phase == "game_over"
    assert ended.final_governor == final_governor
    assert ended.winner == final_governor


# Observation --------------------------------------------------------------


def test_victory_point_chips_are_private_until_the_end() -> None:
    state = start(seed=1)
    p1, p2 = state.order[0], state.order[1]
    state = with_vp_chips(with_vp_chips(state, p1, 5), p2, 3)
    observation = GAME.observe(state, p2)
    data = observation.data
    players = data["players"]
    assert isinstance(players, list)
    for entry in players:
        assert isinstance(entry, dict)
        assert "vp_chips" not in entry
    you = data["you"]
    assert isinstance(you, dict)
    assert you["vp_chips"] == 3
    spectator = GAME.observe(state, None)
    assert spectator.data["you"] is None
    assert GAME.public_scores(state).points[p1] == GAME.scores(state).points[p1] - 5


def test_final_scores_are_revealed_at_game_over() -> None:
    state = start(seed=1)
    p1 = state.order[0]
    state = with_vp_chips(state, p1, 5)
    ended = replace(state, phase="game_over", winner=p1, end_reason="test")
    observation = GAME.observe(ended, state.order[1])
    players = observation.data["players"]
    assert isinstance(players, list)
    assert all(isinstance(entry, dict) and "vp_chips" in entry for entry in players)
    final = observation.data["final_scores"]
    assert isinstance(final, list)


def test_render_text_names_the_viewer() -> None:
    state = start(seed=1)
    text = GAME.render_text(GAME.observe(state, P2))
    assert "You are P2." in text
    assert "Roles:" in text
    assert "Face-up plantations:" in text
    spectator = GAME.render_text(GAME.observe(state, None))
    assert "You are" not in spectator


def test_describe_action_names_the_action() -> None:
    state = start(seed=1)
    observation = GAME.observe(state, state.order[0])
    assert "settler" in GAME.describe_action(observation, SelectRole("settler"))
    assert "indigo" in GAME.describe_action(observation, TakePlantation("indigo"))
    assert "quarry" in GAME.describe_action(observation, TakeQuarry())
    assert "small_indigo_plant" in GAME.describe_action(
        observation, Build("small_indigo_plant")
    )


# Review regressions --------------------------------------------------------


@pytest.mark.parametrize(
    ("num_players", "role"), [(3, "prospector"), (4, "prospector_2")]
)
def test_a_role_missing_from_the_game_is_an_illegal_action_not_a_crash(
    num_players: int, role: Role
) -> None:
    state = start(num_players=num_players, seed=1)
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    action = SelectRole(role)
    assert not space.is_legal(action)
    assert f"no {role} role" in space.explain(action)
    with pytest.raises(IllegalActionError, match="role in this game"):
        GAME.apply(state, decision.player, action)


def test_captain_must_use_the_empty_ship_that_takes_the_most() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=6)
    state = select_role(state, "captain")
    assert notations(state) == ["ship corn s3"]
    state = play(state, "ship corn s3")
    assert goods_get(state.players[player].goods, "corn") == 0


def test_residence_counts_placed_tiles_not_colonists() -> None:
    player = PlayerState(
        plantations=tuple(Plantation("corn", False) for _ in range(12)),
        buildings=(OwnedBuilding("residence", 1),),
    )
    assert end_game_bonus(player) == 7


def test_hospice_colonizes_a_taken_quarry() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    before = state.colonist_supply
    state = select_role(state, "settler")
    state = play(state, "take quarry")
    owner = state.players[player]
    assert owner.quarries == 1
    assert owner.occupied_quarries == 1
    assert state.colonist_supply == before - 1


def test_hospice_colonist_is_optional() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    before = state.colonist_supply
    state = select_role(state, "settler")
    take = next(
        option
        for option in notations(state)
        if option.startswith("take ") and option.endswith("nohospice")
    )
    state = play(state, take)
    assert not state.players[player].plantations[-1].colonized
    assert state.colonist_supply == before


def test_hospice_quarry_colonist_is_optional() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    state = select_role(state, "settler")
    assert "take quarry nohospice" in notations(state)
    state = play(state, "take quarry nohospice")
    assert state.players[player].occupied_quarries == 0


def test_university_colonist_is_optional() -> None:
    state = start(seed=6)
    player = state.order[0]
    state = with_doubloons(state, player, 10)
    state = with_buildings(state, player, OwnedBuilding("university", 1))
    state = select_role(state, "builder")
    assert "build small_indigo_plant nouniversity" in notations(state)
    state = play(state, "build small_indigo_plant nouniversity")
    assert state.players[player].buildings[-1].colonists == 0


def test_declining_a_missing_hospice_or_university_is_explained() -> None:
    state = start(seed=3)
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(TakePlantation(state.face_up[0], use_hospice=False))
        == "You have no active Hospice."
    )
    state = start(seed=6)
    state = select_role(state, "builder")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(Build("small_indigo_plant", use_university=False))
        == "You have no active University."
    )


def test_declining_a_bonus_colonist_with_none_left_is_explained() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("hospice", 1),
        OwnedBuilding("university", 1),
    )
    state = replace(state, colonist_supply=0, colonist_ship=0)
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(TakePlantation(state.face_up[0], use_hospice=False))
        == "There is no colonist available to place."
    )


def test_hospice_and_university_use_the_ship_when_the_supply_is_empty() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hospice", 1))
    state = replace(state, colonist_supply=0, colonist_ship=3)
    state = select_role(state, "settler")
    take = next(
        option
        for option in notations(state)
        if option.startswith("take ") and option != "take quarry"
    )
    state = play(state, take)
    assert state.players[player].plantations[-1].colonized
    assert state.colonist_ship == 2

    state = start(seed=6)
    player = state.order[0]
    state = with_doubloons(state, player, 10)
    state = with_buildings(state, player, OwnedBuilding("university", 1))
    state = replace(state, colonist_supply=0, colonist_ship=3)
    state = select_role(state, "builder")
    state = play(state, "build small_indigo_plant")
    assert state.players[player].buildings[-1].colonists == 1
    assert state.colonist_ship == 2


def test_settler_refill_and_reshuffle_emit_events() -> None:
    state = start(seed=3)
    state = select_role(state, "settler")
    kinds: list[str] = []
    while state.phase == "settler_action":
        (decision,) = GAME.pending_decisions(state)
        transition = GAME.apply(state, decision.player, Pass())
        kinds.extend(event.kind for event in transition.events)
        state = transition.state
    assert "face_up_refilled" in kinds

    state = start(seed=3)
    state = replace(
        state,
        active_role="settler",
        phase="settler_action",
        face_up=(),
        plantation_deck=(),
        plantation_discard=("coffee", "coffee", "coffee", "coffee"),
        players_acted=frozenset(state.order[:-1]),
        active_player=state.order[-1],
    )
    transition = GAME.apply(state, state.order[-1], Pass())
    kinds = [event.kind for event in transition.events]
    assert "plantation_discard_reshuffled" in kinds


def test_hacienda_reshuffle_emits_an_event() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_buildings(state, player, OwnedBuilding("hacienda", 1))
    state = replace(
        state,
        plantation_deck=(),
        plantation_discard=("coffee", "coffee"),
    )
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    transition = GAME.apply(state, decision.player, UseHacienda())
    assert next(event.kind for event in transition.events) == (
        "plantation_discard_reshuffled"
    )


def test_observation_exposes_visible_building_points_only() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("guild_hall", 1),
        OwnedBuilding("indigo_plant", 0),
    )
    data = GAME.observe(state, player).data
    assert "public_points" not in data
    players = data["players"]
    assert isinstance(players, list)
    entry = players[player]
    assert isinstance(entry, dict)
    assert entry["building_points"] == 6
    assert entry["public_points"] == public_points(state.players[player])


def test_take_quarry_explains_a_full_island_before_the_privilege() -> None:
    state = start(seed=3)
    player = state.order[0]
    state = with_plantations(state, player, *(Plantation("corn") for _ in range(12)))
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert space.explain(TakeQuarry()) == "Your island is full."


def test_role_doubloons_and_governor_rotation() -> None:
    state = start(seed=3)
    governor = state.governor
    state = replace_role(
        state, "settler", RoleState("settler", doubloons=2, taken_by=None)
    )
    state = play(state, "role settler")
    assert state.players[governor].doubloons == 2 + 2
    next_governor = state.order[1]
    assert end_round(state).governor == next_governor


def test_ship_refill_uses_empty_building_slots_above_the_player_count() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_buildings(
        state,
        player,
        OwnedBuilding("indigo_plant", 0),
        OwnedBuilding("sugar_mill", 0),
    )
    state = replace(state, colonist_supply=50)
    refilled = refill_colonist_ship(state)
    assert refilled.colonist_ship == 6
    assert refilled.colonist_supply == 44


def test_production_is_limited_by_the_goods_supply() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_plantations(state, player, Plantation("indigo", True))
    state = with_buildings(state, player, OwnedBuilding("small_indigo_plant", 1))
    state = replace(state, goods_supply=(10, 0, 11, 9, 9))
    state, _ = run_production(state, player)
    assert goods_get(state.players[player].goods, "indigo") == 0


def test_craftsman_privilege_needs_a_producible_good_in_the_bank() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_plantations(state, player, Plantation("indigo", True))
    state = with_buildings(state, player, OwnedBuilding("small_indigo_plant", 1))
    state = replace(state, goods_supply=(10, 0, 11, 9, 9))
    assert "privilege indigo" not in [
        GAME.format_action(action)
        for action in craftsman_actions(state, state.players[player])
    ]


def test_one_good_type_per_ship() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, indigo=3, corn=1)
    state = replace(
        state,
        cargo_ships=(
            CargoShip(6, "indigo", 2),
            *(ship for ship in state.cargo_ships[1:]),
        ),
    )
    assert can_ship(state, player, "indigo") == (0,)
    assert can_ship(state, player, "corn") == (1, 2)


def test_wharf_goods_return_to_the_supply() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, sugar=2)
    state = with_buildings(state, player, OwnedBuilding("wharf", 1))
    state = select_role(state, "captain")
    before = goods_get(state.goods_supply, "sugar")
    state = play(state, "wharf sugar")
    assert goods_get(state.goods_supply, "sugar") == before + 2


def test_discard_explanation_names_a_missing_good() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=1)
    state = with_role(state, "captain", player)
    state = replace(
        state,
        phase="captain_discard",
        active_role="captain",
        active_player=player,
        players_acted=frozenset(state.order[1:]),
    )
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert space.explain(DiscardGoods(keep="coffee")) == "You have no coffee."


def test_captain_discard_fallback_keeps_a_good() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=2, indigo=3)
    state = with_role(state, "captain", player)
    state = replace(
        state,
        phase="captain_discard",
        active_role="captain",
        active_player=player,
        players_acted=frozenset(state.order[1:]),
    )
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    fallback = space.default
    assert isinstance(fallback, DiscardGoods)
    assert fallback.keep is not None
    after = GAME.apply(state, decision.player, fallback).state
    assert goods_total(after.players[player].goods) == 1


def test_large_warehouse_protects_two_types() -> None:
    owner = PlayerState(
        goods=goods_from(corn=2, indigo=2, sugar=2),
        buildings=(OwnedBuilding("large_warehouse", 1),),
    )
    actions = [
        action
        for action in discard_actions(owner)
        if isinstance(action, DiscardGoods) and action.protected
    ]
    assert DiscardGoods(("corn", "indigo")) in actions


def test_owned_buildings_are_not_offered_again() -> None:
    state = start(seed=2)
    player = state.order[0]
    state = with_doubloons(state, player, 20)
    state = with_buildings(state, player, OwnedBuilding("small_indigo_plant", 1))
    assert "small_indigo_plant" not in available_to_build(state, player)


def test_governor_tie_break_prefers_the_closer_seat() -> None:
    state = start(seed=1)
    governor = state.governor
    next_seat = state.order[1]
    assert tiebreak_key(state, governor)[1] == 0
    assert tiebreak_key(state, next_seat)[1] < 0


# Full matches -------------------------------------------------------------


def record_match(
    config: PuertoRicoConfig, seed: int, game: PuertoRico
) -> list[LogRecord]:
    sink = MemorySink()
    asyncio.run(
        play_match(
            game,
            config,
            seed,
            random_agents(config.num_players, seed),
            match_id="puerto-rico-test",
            sink=sink,
            clock=FakeClock(),
        )
    )
    return sink.records


def test_same_seed_replays_to_the_same_log() -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=2)
    first = record_match(config, 4, GAME)
    second = record_match(config, 4, GAME)
    assert first == second
    report = replay_match(first)
    assert report.game_id == "puerto_rico"
    assert report.steps > 0


def check_playthrough_state(
    state: PuertoRicoState, initial_goods: int, initial_colonists: int
) -> None:
    assert all(count >= 0 for count in state.goods_supply)
    for player in state.players:
        assert all(count >= 0 for count in player.goods)
        assert player.doubloons >= 0
        assert player.vp_chips >= 0
        assert player.occupied_quarries <= player.quarries
    assert total_goods_on_board(state) == initial_goods
    assert total_colonists(state) == initial_colonists


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_random_playthrough_terminates_and_keeps_invariants(seed: int) -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=2)
    initial = GAME.setup(config, seed).state
    initial_goods = total_goods_on_board(initial)
    initial_colonists = total_colonists(initial)
    final, steps = random_playthrough(
        GAME,
        config,
        seed,
        lambda state: check_playthrough_state(state, initial_goods, initial_colonists),
    )
    assert GAME.is_terminal(final)
    assert final.winner is not None
    assert steps <= 1_000


@pytest.mark.parametrize("seed", [1, 2])
def test_a_natural_full_game_reaches_a_rule_based_end(seed: int) -> None:
    config = PuertoRicoConfig(num_players=3)
    initial = GAME.setup(config, seed).state
    initial_goods = total_goods_on_board(initial)
    initial_colonists = total_colonists(initial)
    final, steps = random_playthrough(
        GAME,
        config,
        seed,
        lambda state: check_playthrough_state(state, initial_goods, initial_colonists),
    )
    assert GAME.is_terminal(final)
    assert final.end_reason is not None
    assert final.end_reason != "round limit reached"
    assert steps <= 2_000
