"""Tests for bonus cards, special actions, faction abilities and variants."""

from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.terra_mystica import (
    BonusSpade,
    Bridge,
    ChaosDoubleTurn,
    ChooseFaction,
    CultistCult,
    GiantsSpades,
    NomadsSandstorm,
    SpecialCult,
    SwarmlingsUpgrade,
    TakeTownTile,
    TerraMysticaConfig,
    WitchesRide,
)
from boardgames.games.terra_mystica.bonus import (
    bonus_income,
    bonus_pass_vp,
    effective_shipping,
)
from boardgames.games.terra_mystica.building import build_dwelling, transform_terrain
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    ScoringAction,
    ScoringTile,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    Building,
    Hex,
    PowerGain,
    TerraMysticaState,
    replace_player,
)
from boardgames.games.terra_mystica.power_gain import take_power_gain
from boardgames.games.terra_mystica.rounds import advance_turn, pass_turn
from boardgames.games.terra_mystica.spade_gain import gain_spade_power
from boardgames.games.terra_mystica.spades import cult_spade_actions
from boardgames.games.terra_mystica.special import special_actions
from tests.games.terra_mystica.support import (
    GAME,
    action_state,
    listing,
    start,
    with_resources,
)


def _playing(
    *,
    players: int = 2,
    seed: int = 1,
    rounds: int = 1,
    bonus_cards: bool = False,
    faction_choice: bool = False,
    variable_points: bool = False,
    promo_town_tiles: bool = False,
    fixed_setup: bool = False,
) -> TerraMysticaState:
    state = GAME.setup(
        TerraMysticaConfig(
            num_players=players,
            rounds=rounds,
            bonus_cards=bonus_cards,
            faction_choice=faction_choice,
            variable_points=variable_points,
            promo_town_tiles=promo_town_tiles,
            fixed_setup=fixed_setup,
        ),
        seed,
    ).state
    while state.phase in ("faction_choice", "setup", "bonus_choice"):
        (decision,) = GAME.pending_decisions(state)
        actions = GAME.legal_actions(state, decision).listing(10_000)
        assert actions
        state = GAME.apply(state, decision.player, actions[0]).state
    return state


def _special_state(
    faction: FactionType,
) -> tuple[TerraMysticaState, PlayerId, Hex]:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = action_state(state, player, (position, BuildingType.STRONGHOLD))
    state = replace_player(
        state, player, replace(state.players[player], faction=faction)
    )
    return state, player, position


def _empty_land(state: TerraMysticaState, terrain: Terrain | None = None) -> Hex:
    return next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and (terrain is None or tile.terrain is terrain)
    )


def test_faction_choice_and_fixed_setup() -> None:
    state = GAME.setup(
        TerraMysticaConfig(
            num_players=3, rounds=1, faction_choice=True, bonus_cards=False
        ),
        1,
    ).state
    assert state.phase == "faction_choice"
    first = state.active_player
    assert ChooseFaction(FactionType.WITCHES) in listing(state)
    state = GAME.apply(state, first, ChooseFaction(FactionType.WITCHES)).state
    assert state.players[first].faction is FactionType.WITCHES
    assert ChooseFaction(FactionType.AUREN) not in listing(state)

    fixed = GAME.setup(
        TerraMysticaConfig(
            num_players=2,
            rounds=1,
            fixed_setup=True,
            faction_choice=True,
            bonus_cards=False,
        ),
        1,
    ).state
    assert fixed.phase == "setup"
    assert {player.faction for player in fixed.players} == {
        FactionType.WITCHES,
        FactionType.NOMADS,
    }


def test_variable_points_and_bonus_draft() -> None:
    variable = GAME.setup(
        TerraMysticaConfig(
            num_players=2,
            rounds=1,
            variable_points=True,
            faction_choice=False,
            bonus_cards=False,
        ),
        1,
    ).state
    assert any(player.victory_points != 20 for player in variable.players)

    state = _playing(rounds=2, bonus_cards=True, variable_points=True)
    assert state.phase == "action"
    assert all(player.bonus_card is not None for player in state.players)
    assert len(state.bonus_available) == 3
    assert all(state.bonus_coins[index] == 1 for index in state.bonus_available)


def test_bonus_income_pass_vp_and_shipping() -> None:
    state = _playing(rounds=2, bonus_cards=True)
    player = state.order[0]
    state = replace_player(state, player, replace(state.players[player], bonus_card=0))
    assert bonus_income(state.players[player]).priests == 1

    position = _empty_land(state)
    state = replace(
        state,
        board=state.board.place(position, Building(BuildingType.DWELLING, player)),
    )
    state = replace_player(state, player, replace(state.players[player], bonus_card=6))
    assert bonus_pass_vp(state, player) >= 1

    state = replace_player(state, player, replace(state.players[player], bonus_card=3))
    assert effective_shipping(state, player) == state.players[player].shipping + 1


def test_bonus_special_actions_are_listed() -> None:
    state = _playing(rounds=2, bonus_cards=True)
    player = state.order[0]
    state = replace_player(state, player, replace(state.players[player], bonus_card=4))
    assert any(
        type(action).__name__ == "BonusSpade"
        for action in special_actions(state, player)
    )
    state = replace_player(state, player, replace(state.players[player], bonus_card=5))
    assert any(
        isinstance(action, SpecialCult) and action.source == "bonus"
        for action in special_actions(state, player)
    )


def test_water_favor_special_action_is_per_holder() -> None:
    state = start(num_players=2, seed=1)
    first, second = state.order
    for player in (first, second):
        state = replace_player(
            state,
            player,
            replace(state.players[player], favors=frozenset({5})),
        )
    state = action_state(state, first)
    state = GAME.apply(state, first, SpecialCult("water_favor", Cult.FIRE)).state
    assert any(
        isinstance(action, SpecialCult) and action.source == "water_favor"
        for action in special_actions(state, second)
    )


def test_auren_and_water_favor_cult_actions() -> None:
    state, player, _ = _special_state(FactionType.AUREN)
    assert any(
        isinstance(action, SpecialCult) and action.source == "auren"
        for action in special_actions(state, player)
    )
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({5})),
    )
    assert any(
        isinstance(action, SpecialCult) and action.source == "water_favor"
        for action in special_actions(state, player)
    )


def test_auren_stronghold_grants_a_favor() -> None:
    from boardgames.games.terra_mystica.strongholds import stronghold_reward

    state, player, _ = _special_state(FactionType.AUREN)
    state, _events = stronghold_reward(state, player, [])
    assert state.phase == "favor_choice"
    assert state.pending_favors == 1


def test_special_cult_and_bonus_spade_apply() -> None:
    state, player, _ = _special_state(FactionType.AUREN)
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({5})),
    )
    before = state.players[player].cult(Cult.FIRE)
    state = GAME.apply(state, player, SpecialCult("water_favor", Cult.FIRE)).state
    assert state.players[player].cult(Cult.FIRE) == before + 1

    bonus = _playing(rounds=2, bonus_cards=True)
    bonus_player = bonus.order[0]
    bonus = replace_player(
        bonus,
        bonus_player,
        replace(bonus.players[bonus_player], bonus_card=4),
    )
    from boardgames.games.terra_mystica import BonusSpade

    bonus = GAME.apply(bonus, bonus_player, BonusSpade()).state
    assert bonus.phase == "cult_spades"
    assert bonus.cult_spades[bonus_player] == 1


def test_witches_ride_is_a_free_forest_build() -> None:
    state, player, _ = _special_state(FactionType.WITCHES)
    forest = _empty_land(state, state.players[player].home_terrain)
    assert WitchesRide(forest) in special_actions(state, player)
    before = state.players[player].resources.coins
    state = GAME.apply(state, player, WitchesRide(forest)).state
    tile = state.board.tile(forest)
    assert tile is not None and tile.building is not None
    assert state.players[player].resources.coins == before


def test_swarmlings_upgrade_and_chaos_double_turn() -> None:
    state, player, _ = _special_state(FactionType.SWARMLINGS)
    dwelling = _empty_land(state)
    state = replace(
        state,
        board=state.board.place(dwelling, Building(BuildingType.DWELLING, player)),
    )
    assert SwarmlingsUpgrade(dwelling) in special_actions(state, player)
    state = GAME.apply(state, player, SwarmlingsUpgrade(dwelling)).state
    tile = state.board.tile(dwelling)
    assert tile is not None and tile.building is not None
    assert tile.building.type is BuildingType.TRADING_HOUSE

    chaos, chaos_player, _ = _special_state(FactionType.CHAOS_MAGICIANS)
    assert ChaosDoubleTurn() in special_actions(chaos, chaos_player)
    chaos = GAME.apply(chaos, chaos_player, ChaosDoubleTurn()).state
    assert chaos.extra_actions == 2
    chaos = advance_turn(chaos, chaos_player, ()).state
    assert chaos.active_player == chaos_player
    assert chaos.extra_actions == 1
    chaos = advance_turn(chaos, chaos_player, ()).state
    assert chaos.active_player != chaos_player
    assert chaos.extra_actions == 0


def test_giants_and_nomads_transform_specials() -> None:
    giants, giants_player, _ = _special_state(FactionType.GIANTS)
    target = next(
        tile.position
        for tile in giants.board.tiles
        if tile.is_land
        and tile.building is None
        and tile.terrain is not giants.players[giants_player].home_terrain
        and tile.position in giants.board.reachable_land(giants_player, 0, 0, ())
    )
    giants = replace(
        giants,
        scoring=(ScoringTile(ScoringAction.SPADE, CultBonus(Cult.FIRE, 4, "power")),),
    )
    assert GiantsSpades(target) in special_actions(giants, giants_player)
    before = giants.players[giants_player].victory_points
    giants = GAME.apply(giants, giants_player, GiantsSpades(target)).state
    tile = giants.board.tile(target)
    assert tile is not None
    assert tile.terrain is giants.players[giants_player].home_terrain
    assert giants.players[giants_player].victory_points == before + 4

    nomads, nomads_player, stronghold = _special_state(FactionType.NOMADS)
    target = next(
        neighbour
        for neighbour in stronghold.neighbours()
        if (tile := nomads.board.tile(neighbour)) is not None
        and tile.is_land
        and tile.building is None
        and tile.terrain is not nomads.players[nomads_player].home_terrain
    )
    assert NomadsSandstorm(target) in special_actions(nomads, nomads_player)
    nomads = GAME.apply(nomads, nomads_player, NomadsSandstorm(target)).state
    tile = nomads.board.tile(target)
    assert tile is not None
    assert tile.terrain is nomads.players[nomads_player].home_terrain


def test_alchemist_spade_power() -> None:
    state, player, _ = _special_state(FactionType.ALCHEMISTS)
    state = with_resources(state, player, power1=5, power2=0, power3=0)
    state = gain_spade_power(state, player, 2)
    resources = state.players[player].resources
    assert resources.power1 == 1
    assert resources.power2 == 4

    state, player, stronghold = _special_state(FactionType.ALCHEMISTS)
    target = next(
        neighbour
        for neighbour in stronghold.neighbours()
        if (tile := state.board.tile(neighbour)) is not None
        and tile.is_land
        and tile.building is None
        and tile.terrain is not state.players[player].home_terrain
    )
    state = with_resources(state, player, power1=10, power2=0, power3=0)
    state = transform_terrain(state, player, target).state
    assert state.players[player].resources.power1 < 10
    assert state.players[player].resources.power2 > 0


def test_halfling_bonus_spade_scores() -> None:
    state = _playing(rounds=2, bonus_cards=True)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.HALFLINGS,
            bonus_card=4,
        ),
    )
    before = state.players[player].victory_points
    state = GAME.apply(state, player, BonusSpade()).state
    assert state.players[player].victory_points == before + 1


def test_shipping_bonus_does_not_apply_to_cult_spades() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    start_position = None
    target = None
    for tile in state.board.tiles:
        if not tile.is_land:
            continue
        for river in tile.position.neighbours():
            river_tile = state.board.tile(river)
            if river_tile is None or river_tile.is_land:
                continue
            for neighbour in river.neighbours():
                other = state.board.tile(neighbour)
                if (
                    other is not None
                    and other.is_land
                    and other.building is None
                    and tile.position.distance(other.position) == 2
                    and other.terrain is not state.players[player].home_terrain
                ):
                    start_position, target = tile.position, neighbour
                    break
            if target is not None:
                break
        if target is not None:
            break
    assert start_position is not None and target is not None
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(state, player, replace(state.players[player], bonus_card=3))
    state = replace(
        state,
        phase="cult_spades",
        spade_return="round",
        spade_actor=player,
        cult_spades=tuple(1 if seat == player else 0 for seat in range(2)),
        active_player=player,
    )
    assert target not in {
        action.position
        for action in cult_spade_actions(state, player)
        if hasattr(action, "position")
    }
    action_state_round = replace(state, spade_return="action")
    assert target in {
        action.position
        for action in cult_spade_actions(action_state_round, player)
        if hasattr(action, "position")
    }


def test_engineers_pass_scores_bridges() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    first, second = next(
        (tile.position, neighbour)
        for tile in state.board.tiles
        for neighbour in tile.position.neighbours()
        if (other := state.board.tile(neighbour)) is not None
        and other.is_land
        and tile.position < neighbour
    )
    state = action_state(state, player, (first, BuildingType.STRONGHOLD))
    state = replace(
        state,
        board=state.board.place(second, Building(BuildingType.DWELLING, player)),
        bridges=(Bridge(player, first, second),),
    )
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.ENGINEERS)
    )
    before = state.players[player].victory_points
    state = pass_turn(state, player).state
    assert state.players[player].victory_points == before + 3


def test_promo_town_tiles() -> None:
    state = _playing(rounds=1, promo_town_tiles=True)
    assert len(state.town_tiles) == 8
    player = state.order[0]
    state = replace(state, phase="town_choice", pending_towns=1)
    owner = replace(state.players[player], keys=1)
    state = replace_player(state, player, owner)
    before = state.players[player]
    state = GAME.apply(state, player, TakeTownTile(5)).state
    after = state.players[player]
    assert after.keys == before.keys + 1
    assert after.keys == 2
    assert all(after.cult(cult) == before.cult(cult) + 2 for cult in Cult)


def test_cultists_choose_a_cult_after_power_is_taken() -> None:
    state = start(num_players=2, seed=1)
    builder, opponent = state.order
    target = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and len(
            [
                neighbour
                for neighbour in tile.position.neighbours()
                if (other := state.board.tile(neighbour)) is not None and other.is_land
            ]
        )
        >= 2
    )
    neighbours = [
        neighbour
        for neighbour in target.neighbours()
        if (tile := state.board.tile(neighbour)) is not None and tile.is_land
    ]
    support, opponent_tile = neighbours[:2]
    state = action_state(state, builder, (support, BuildingType.TRADING_HOUSE))
    state = replace(
        state,
        board=state.board.place(
            opponent_tile, Building(BuildingType.DWELLING, opponent)
        ),
    )
    state = replace_player(
        state,
        builder,
        replace(state.players[builder], faction=FactionType.CULTISTS),
    )
    state = with_resources(state, opponent, power1=3, power2=9, power3=0)
    state = build_dwelling(state, builder, target).state
    assert state.phase == "power_gain"
    state = take_power_gain(state, opponent, True).state
    assert state.phase == "cultist_cult"
    before = state.players[builder].cult(Cult.FIRE)
    state = GAME.apply(state, builder, CultistCult(Cult.FIRE)).state
    assert state.players[builder].cult(Cult.FIRE) == before + 1

    decline = start(num_players=2, seed=1)
    builder, opponent = decline.order
    decline = action_state(
        decline,
        builder,
        (
            next(
                tile.position
                for tile in decline.board.tiles
                if tile.is_land and tile.building is None
            ),
            BuildingType.STRONGHOLD,
        ),
    )
    decline = replace_player(
        decline,
        builder,
        replace(decline.players[builder], faction=FactionType.CULTISTS),
    )
    decline = with_resources(decline, builder, power1=5, power2=0, power3=0)
    decline = with_resources(decline, opponent, power1=3, power2=9, power3=0)
    decline = replace(
        decline,
        pending_power=(
            PowerGain(
                opponent,
                1,
                Hex(0, 0),
                BuildingType.DWELLING,
                builder,
            ),
        ),
        power_actor=builder,
        phase="power_gain",
        active_player=opponent,
        cultist_offered=True,
        cultist_taken=False,
        cultist_actor=builder,
    )
    decline = take_power_gain(decline, opponent, False).state
    assert decline.phase == "action"
    assert decline.players[builder].resources.power1 < 5
