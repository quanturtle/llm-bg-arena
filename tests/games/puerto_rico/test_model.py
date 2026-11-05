"""Tests for the Puerto Rico model queries: production, prices, costs and points."""

from dataclasses import replace

from boardgames.games.puerto_rico.model import (
    CargoShip,
    OwnedBuilding,
    Plantation,
    PlayerState,
    available_to_build,
    build_cost,
    building_points,
    can_ship,
    end_game_bonus,
    factory_bonus_for_produced,
    goods_from,
    production,
    replace_player,
    sell_price,
    ship_victory_points,
    total_points,
)
from tests.games.puerto_rico.support import (
    start,
    with_buildings,
    with_doubloons,
    with_goods,
    with_quarries,
    with_role,
)


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


def test_residence_counts_placed_tiles_not_colonists() -> None:
    player = PlayerState(
        plantations=tuple(Plantation("corn", False) for _ in range(12)),
        buildings=(OwnedBuilding("residence", 1),),
    )
    assert end_game_bonus(player) == 7


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


def test_owned_buildings_are_not_offered_again() -> None:
    state = start(seed=2)
    player = state.order[0]
    state = with_doubloons(state, player, 20)
    state = with_buildings(state, player, OwnedBuilding("small_indigo_plant", 1))
    assert "small_indigo_plant" not in available_to_build(state, player)
