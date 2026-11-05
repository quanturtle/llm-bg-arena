"""Tests for the Puerto Rico Captain: shipping, the Wharf and the discard step."""

from dataclasses import replace

from boardgames.games.puerto_rico import DiscardGoods, Pass
from boardgames.games.puerto_rico.model import (
    CargoShip,
    OwnedBuilding,
    PlayerState,
    goods_from,
    goods_get,
)
from boardgames.games.puerto_rico.roles.captain import discard_actions
from tests.games.puerto_rico.support import (
    GAME,
    drain,
    notations,
    play,
    select_role,
    start,
    with_buildings,
    with_goods,
    with_role,
)


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


def test_captain_must_use_the_empty_ship_that_takes_the_most() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=6)
    state = select_role(state, "captain")
    assert notations(state) == ["ship corn s3"]
    state = play(state, "ship corn s3")
    assert goods_get(state.players[player].goods, "corn") == 0


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
