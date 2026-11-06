"""Tests for Terra Mystica spade phases: cult-bonus spades and action spades."""

from dataclasses import replace

import pytest

from boardgames.core import IllegalActionError, PlayerId
from boardgames.games.terra_mystica import (
    BuildDwelling,
    Building,
    Hex,
    PowerAction,
    SkipCultSpade,
    TerraMysticaState,
    TradeVpForCoin,
    UseCultSpade,
)
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    Resources,
    ScoringAction,
    ScoringTile,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    replace_at,
    replace_player,
    spades_for,
    terrain_toward,
)
from tests.games.terra_mystica.support import (
    GAME,
    _mermaid_gap_state,
    _neutral_scoring,
    action_state,
    empty_land_tiles,
    listing,
    play,
    play_setup,
    start,
    with_resources,
)


def test_cult_spade_bonus_is_a_player_choice() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    spade_tile = ScoringTile(
        ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")
    )
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = replace(state, scoring=(spade_tile, priest_tile))
    state = replace(
        state,
        players=tuple(replace(player, cults=(9, 9, 9, 9)) for player in state.players),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")

    assert state.phase == "cult_spades"
    (decision,) = GAME.pending_decisions(state)
    spade = next(
        action
        for action in listing(state)
        if isinstance(action, UseCultSpade) and action.to is None
    )
    home = state.players[decision.player].home_terrain
    state = GAME.apply(state, decision.player, spade).state
    tile = state.board.tile(spade.position)
    assert tile is not None and tile.terrain is home

    while state.phase == "cult_spades":
        state = play(state, "skip spade")
    assert state.round == 2
    assert state.phase == "action"


def cult_spade_points(faction: FactionType) -> tuple[int, int]:
    """Points and spades for the first cult-bonus spade a faction uses."""
    spade_tile = ScoringTile(
        ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")
    )
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    state = replace(state, scoring=(spade_tile, priest_tile))
    state = replace(
        state,
        players=tuple(
            replace(player, faction=faction, cults=(9, 9, 9, 9))
            for player in state.players
        ),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    (decision,) = GAME.pending_decisions(state)
    spade = next(
        action
        for action in listing(state)
        if isinstance(action, UseCultSpade) and action.to is None
    )
    tile = state.board.tile(spade.position)
    assert tile is not None
    player = state.players[decision.player]
    cost = spades_for(player.profile, tile.terrain)
    before = player.victory_points
    state = GAME.apply(state, decision.player, spade).state
    return state.players[decision.player].victory_points - before, cost


def test_cult_spade_points_follow_the_faction_bonus() -> None:
    gained, _cost = cult_spade_points(FactionType.HALFLINGS)
    assert gained == 0
    gained, _ = cult_spade_points(FactionType.DARKLINGS)
    assert gained == 0


def test_giants_forfeit_a_single_cult_spade() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    spade_tile = ScoringTile(
        ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")
    )
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = replace(state, scoring=(spade_tile, priest_tile))
    state = replace(
        state,
        players=tuple(
            replace(player, faction=FactionType.GIANTS, cults=(9, 9, 9, 9))
            for player in state.players
        ),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    assert state.phase == "cult_spades"
    (decision,) = GAME.pending_decisions(state)
    state = replace(
        state,
        cult_spades=replace_at(state.cult_spades, decision.player, 1),
    )
    assert not any(isinstance(action, UseCultSpade) for action in listing(state))
    assert SkipCultSpade() in listing(state)


def test_spade_power_action_opens_a_spade_phase() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, power1=0, power2=0, power3=12)
    assert PowerAction("spade") in listing(state)
    assert PowerAction("double_spade") in listing(state)
    state = GAME.apply(state, player, PowerAction("spade")).state
    assert state.phase == "cult_spades"
    assert state.cult_spades[player] == 1
    assert "spade" in state.used_power_actions
    state = GAME.apply(state, player, SkipCultSpade()).state
    assert state.phase == "action"
    assert state.active_player != player


def test_spade_build_is_not_listed_without_a_dwelling() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = empty_land_tiles(state)
    board = state.board
    for position in positions[:8]:
        board = board.place(position, Building(BuildingType.DWELLING, player))
    target = positions[8]
    state = replace(
        state,
        board=board,
        phase="cult_spades",
        cult_spades=replace_at(state.cult_spades, player, 0),
        spade_return="action",
        spade_actor=player,
        power_spade_tiles=(target,),
        active_player=player,
    )
    assert BuildDwelling(target) not in listing(state)
    assert SkipCultSpade() in listing(state)


def test_empty_action_spade_phase_advances_without_a_prompt() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.WITCHES, 1)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.LAKE)),
    )
    state = with_resources(state, player, coins=0, workers=3, priests=0)
    transition = GAME.apply(state, player, UseCultSpade(first))
    after = transition.state
    assert after.phase == "action"
    assert after.active_player != player
    assert not any(event.kind == "cult_spade_skipped" for event in transition.events)


def test_alchemist_empty_action_spade_phase_stays_open_for_trade() -> None:
    state, player, _start, first, _second = _action_spade_state(
        FactionType.ALCHEMISTS, 1
    )
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.LAKE)),
    )
    state = with_resources(state, player, coins=0, workers=3, priests=0)
    after = GAME.apply(state, player, UseCultSpade(first)).state
    assert after.phase == "cult_spades"
    assert after.active_player == player
    assert TradeVpForCoin() in listing(after)


def _adjacent_empty_pair(
    state: TerraMysticaState,
) -> tuple[Hex, Hex, Hex]:
    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        empty = [
            neighbour
            for neighbour in tile.position.neighbours()
            if (other := state.board.tile(neighbour)) is not None
            and other.is_land
            and other.building is None
        ]
        if len(empty) >= 2:
            return tile.position, empty[0], empty[1]
    raise AssertionError("no tile with two empty land neighbours")


def _adjacent_empty_triple(
    state: TerraMysticaState,
) -> tuple[Hex, Hex, Hex, Hex]:
    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        empty = [
            neighbour
            for neighbour in tile.position.neighbours()
            if (other := state.board.tile(neighbour)) is not None
            and other.is_land
            and other.building is None
        ]
        if len(empty) >= 3:
            return tile.position, empty[0], empty[1], empty[2]
    raise AssertionError("no tile with three empty land neighbours")


def _action_spade_state(
    faction: FactionType, budget: int, *, seed: int = 1
) -> tuple[TerraMysticaState, PlayerId, Hex, Hex, Hex]:
    state = start(num_players=2, seed=seed)
    player = state.order[0]
    start_position, first, second = _adjacent_empty_pair(state)
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=faction,
            resources=Resources(coins=50, workers=50, priests=10, power1=5, power2=7),
        ),
    )
    state = _neutral_scoring(state)
    state = replace(
        state,
        phase="cult_spades",
        spade_return="action",
        spade_actor=player,
        cult_spades=replace_at(state.cult_spades, player, budget),
        power_spade_tiles=(),
        spade_second=None,
        spade_topup=True,
        spade_require_all=False,
        active_player=player,
    )
    return state, player, start_position, first, second


def test_action_phase_spades_score_spade_round_points() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.WITCHES,
            resources=Resources(
                coins=50, workers=50, priests=10, power1=0, power2=0, power3=12
            ),
        ),
    )
    state = replace(
        state,
        scoring=(ScoringTile(ScoringAction.SPADE, CultBonus(Cult.AIR, 4, "spades")),),
    )
    state = GAME.apply(state, player, PowerAction("spade")).state
    action = next(
        action for action in listing(state) if isinstance(action, UseCultSpade)
    )
    tile = state.board.tile(action.position)
    assert tile is not None
    cost = spades_for(state.players[player].profile, tile.terrain)
    before = state.players[player].victory_points
    after = GAME.apply(state, player, action).state
    assert after.players[player].victory_points - before == cost * 2


def test_giants_one_spade_power_action_is_not_only_a_skip() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.GIANTS,
            resources=Resources(
                coins=15, workers=3, priests=0, power1=0, power2=0, power3=12
            ),
        ),
    )
    state = GAME.apply(state, player, PowerAction("spade")).state
    assert any(isinstance(action, UseCultSpade) for action in listing(state))


def test_power_spade_pays_workers_for_missing_spades() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.GIANTS, 1)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.FOREST)),
    )
    assert UseCultSpade(first) in listing(state)
    before = state.players[player].resources
    after = GAME.apply(state, player, UseCultSpade(first)).state
    tile = after.board.tile(first)
    assert tile is not None and tile.terrain is Terrain.WASTELAND
    assert after.players[player].resources.workers == before.workers - 3


def test_topped_up_spades_score_faction_victory_points() -> None:
    state, player, _start, first, _second = _action_spade_state(
        FactionType.DARKLINGS, 1
    )
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.FOREST)),
    )
    before = state.players[player]
    assert UseCultSpade(first) in listing(state)
    after = GAME.apply(state, player, UseCultSpade(first)).state
    assert after.players[player].resources.priests == before.resources.priests - 1
    assert after.players[player].victory_points == before.victory_points + 2


def test_halfling_topped_up_spades_score_faction_victory_points() -> None:
    state, player, _start, first, _second = _action_spade_state(
        FactionType.HALFLINGS, 1
    )
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.LAKE)),
    )
    before = state.players[player]
    assert UseCultSpade(first) in listing(state)
    after = GAME.apply(state, player, UseCultSpade(first)).state
    assert after.players[player].resources.workers == before.resources.workers - 3
    assert after.players[player].victory_points == before.victory_points + 1


def test_action_spade_can_stop_at_an_intermediate_terrain() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.WITCHES, 1)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.PLAINS)),
    )
    action = UseCultSpade(first, Terrain.SWAMP)
    assert action in listing(state)
    after = GAME.apply(state, player, action).state
    tile = after.board.tile(first)
    assert tile is not None and tile.terrain is Terrain.SWAMP
    assert after.cult_spades[player] == 0
    assert not any(isinstance(candidate, BuildDwelling) for candidate in listing(after))


def test_power_spade_description_says_already_paid() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.WITCHES, 1)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.LAKE)),
    )
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, UseCultSpade(first))
    assert "1 spade, already paid" in description
    assert "workers" not in description


def test_cult_spade_description_says_already_paid() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.WITCHES, 1)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.LAKE)),
        spade_return="round",
        spade_actor=None,
    )
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, UseCultSpade(first))
    assert "cult-bonus spade" in description
    assert "1 spade, already paid" in description
    assert "workers" not in description


def test_spade_description_shows_only_missing_spades() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.WITCHES, 1)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.SWAMP)),
    )
    observation = GAME.observe(state, player)
    description = GAME.describe_action(observation, UseCultSpade(first))
    assert "2 spades; 1 spade missing = 3 workers" in description


def test_non_home_partial_stop_must_use_all_remaining_spades() -> None:
    state, player, _start, first, _second = _action_spade_state(FactionType.WITCHES, 2)
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.PLAINS)),
    )
    action = UseCultSpade(first, Terrain.SWAMP)
    assert action not in listing(state)
    with pytest.raises(IllegalActionError):
        GAME.apply(state, player, action)


def test_darklings_can_top_up_the_first_non_home_spade_and_score() -> None:
    state, player, _start, first, _second = _action_spade_state(
        FactionType.DARKLINGS, 1
    )
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.PLAINS)),
    )
    action = UseCultSpade(first, Terrain.LAKE)
    assert action in listing(state)
    before = state.players[player]
    after = GAME.apply(state, player, action).state
    tile = after.board.tile(first)
    assert tile is not None and tile.terrain is Terrain.LAKE
    assert after.players[player].resources.priests == before.resources.priests - 1
    assert after.players[player].victory_points == before.victory_points + 2
    assert after.phase == "action"


def test_second_action_spade_tile_can_stop_at_non_home_terrain() -> None:
    state, player, _start, first, second = _action_spade_state(FactionType.WITCHES, 2)
    board = state.board
    for position, terrain in ((first, Terrain.LAKE), (second, Terrain.PLAINS)):
        tile = board.tile(position)
        assert tile is not None
        board = board.replace_tile(position, replace(tile, terrain=terrain))
    state = replace(state, board=board)
    state = GAME.apply(state, player, UseCultSpade(first)).state
    action = UseCultSpade(second, Terrain.SWAMP)
    assert action in listing(state)
    after = GAME.apply(state, player, action).state
    tile = after.board.tile(second)
    assert tile is not None and tile.terrain is Terrain.SWAMP
    assert after.spade_second == second
    assert not any(
        candidate.position == second
        for candidate in listing(after)
        if isinstance(candidate, BuildDwelling)
    )


def test_action_spade_cannot_tunnel_twice_in_one_action() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    start_position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and len(
            [
                other
                for other in state.board.tiles
                if other.is_land
                and other.building is None
                and other.position.distance(tile.position) == 2
                and other.terrain is not Terrain.MOUNTAIN
            ]
        )
        >= 2
    )
    targets = [
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and tile.position.distance(start_position) == 2
        and tile.terrain is not Terrain.MOUNTAIN
    ][:2]
    assert len(targets) == 2
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.DWARVES,
            resources=Resources(coins=50, workers=50, priests=10),
        ),
    )
    board = state.board
    for position in targets:
        tile = board.tile(position)
        assert tile is not None
        board = board.replace_tile(position, replace(tile, terrain=Terrain.FOREST))
    state = _neutral_scoring(
        replace(
            state,
            board=board,
            phase="cult_spades",
            spade_return="action",
            spade_actor=player,
            cult_spades=replace_at(state.cult_spades, player, 2),
            power_spade_tiles=(),
            spade_second=None,
            spade_topup=True,
            spade_require_all=False,
            active_player=player,
        )
    )
    first, second = targets
    state = GAME.apply(state, player, UseCultSpade(first)).state
    assert state.spade_reach_used
    assert UseCultSpade(second) not in listing(state)
    with pytest.raises(IllegalActionError):
        GAME.apply(state, player, UseCultSpade(second))


def test_only_the_first_action_spade_tile_can_be_topped_up() -> None:
    state, player, _start, first, second = _action_spade_state(FactionType.WITCHES, 2)
    board = state.board
    for position, terrain in ((first, Terrain.LAKE), (second, Terrain.SWAMP)):
        tile = board.tile(position)
        assert tile is not None
        board = board.replace_tile(position, replace(tile, terrain=terrain))
    state = replace(state, board=board)
    state = GAME.apply(state, player, UseCultSpade(first)).state
    assert state.cult_spades[player] == 1
    assert not any(
        action.position == second and action.to is None
        for action in listing(state)
        if isinstance(action, UseCultSpade)
    )
    with pytest.raises(IllegalActionError):
        GAME.apply(state, player, UseCultSpade(second))


def test_power_spades_reach_through_tunneling() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    start_position, target = next(
        (tile.position, other.position)
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
        for other in state.board.tiles
        if other.is_land
        and other.building is None
        and other.terrain is not Terrain.MOUNTAIN
        and tile.position.distance(other.position) == 2
    )
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.DWARVES,
            resources=Resources(coins=50, workers=50, priests=10),
        ),
    )
    state = _neutral_scoring(state)
    state = replace(
        state,
        phase="cult_spades",
        spade_return="action",
        spade_actor=player,
        cult_spades=replace_at(state.cult_spades, player, 2),
        power_spade_tiles=(),
        spade_second=None,
        spade_topup=True,
        active_player=player,
    )
    assert UseCultSpade(target) in listing(state)
    before = state.players[player]
    after = GAME.apply(state, player, UseCultSpade(target)).state
    tile = after.board.tile(target)
    assert tile is not None and tile.terrain is Terrain.MOUNTAIN
    assert BuildDwelling(target) in listing(after)
    after = GAME.apply(after, player, BuildDwelling(target)).state
    assert after.players[player].resources.workers == before.resources.workers - 3
    assert after.players[player].victory_points == before.victory_points + 4


def test_action_phase_spades_use_a_single_tile_then_one_extra() -> None:
    state, player, _start, first, second = _action_spade_state(FactionType.WITCHES, 2)
    board = state.board
    for position in (first, second):
        tile = board.tile(position)
        assert tile is not None
        board = board.replace_tile(position, replace(tile, terrain=Terrain.LAKE))
    state = replace(state, board=board)
    actions = listing(state)
    assert any(
        action.to is None for action in actions if isinstance(action, UseCultSpade)
    )
    state = GAME.apply(state, player, UseCultSpade(first)).state
    assert state.spade_second is None
    actions = listing(state)
    assert UseCultSpade(second) in actions
    assert not any(
        action.position == first
        for action in actions
        if isinstance(action, UseCultSpade)
    )
    state = GAME.apply(state, player, UseCultSpade(second)).state
    assert state.spade_second == second
    assert BuildDwelling(first) in listing(state)
    assert BuildDwelling(second) not in listing(state)
    assert not any(isinstance(action, UseCultSpade) for action in listing(state))


def test_halfling_stronghold_spades_reach_three_tiles_and_all_can_build() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    start_position, first, second, third = _adjacent_empty_triple(state)
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.HALFLINGS,
            resources=Resources(coins=50, workers=50, priests=10),
        ),
    )
    board = state.board
    for position in (first, second, third):
        tile = board.tile(position)
        assert tile is not None
        board = board.replace_tile(position, replace(tile, terrain=Terrain.SWAMP))
    state = _neutral_scoring(
        replace(
            state,
            board=board,
            phase="cult_spades",
            spade_return="action",
            spade_actor=player,
            cult_spades=replace_at(state.cult_spades, player, 3),
            power_spade_tiles=(),
            spade_second=None,
            spade_transformed=(),
            spade_intermediate=False,
            spade_reach_used=False,
            spade_topup=False,
            spade_require_all=True,
            active_player=player,
        )
    )
    for position in (first, second, third):
        assert UseCultSpade(position) in listing(state)
        state = GAME.apply(state, player, UseCultSpade(position)).state
    assert state.cult_spades[player] == 0
    for position in (first, second, third):
        assert BuildDwelling(position) in listing(state)
    state = GAME.apply(state, player, BuildDwelling(second)).state
    assert state.phase == "action"
    built = state.board.tile(second)
    assert built is not None and built.building is not None


def test_halfling_stronghold_spades_can_stop_short_of_home() -> None:
    state, player, _start, first, _second = _action_spade_state(
        FactionType.HALFLINGS, 3
    )
    tile = state.board.tile(first)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(first, replace(tile, terrain=Terrain.SWAMP)),
        spade_require_all=True,
        spade_topup=False,
    )
    action = UseCultSpade(first, Terrain.LAKE)
    assert action in listing(state)
    after = GAME.apply(state, player, action).state
    tile = after.board.tile(first)
    assert tile is not None and tile.terrain is Terrain.LAKE
    assert after.cult_spades[player] == 2
    assert BuildDwelling(first) not in listing(after)


def test_halflings_can_drop_leftover_stronghold_spades_and_still_build() -> None:
    state, player, _start, first, _second = _action_spade_state(
        FactionType.HALFLINGS, 3
    )
    tile = state.board.tile(first)
    assert tile is not None
    state = _neutral_scoring(
        replace(
            state,
            board=state.board.replace_tile(first, replace(tile, terrain=Terrain.SWAMP)),
            spade_require_all=True,
            spade_topup=False,
        )
    )
    state = GAME.apply(state, player, UseCultSpade(first)).state
    assert state.cult_spades[player] == 2
    state = GAME.apply(state, player, SkipCultSpade()).state
    assert state.cult_spades[player] == 0
    assert BuildDwelling(first) in listing(state)
    state = GAME.apply(state, player, BuildDwelling(first)).state
    assert state.phase == "action"
    built = state.board.tile(first)
    assert built is not None and built.building is not None


def test_post_spade_build_lists_mermaid_rivers_and_alchemist_trades() -> None:
    state, player, target, river = _mermaid_gap_state()
    tile = state.board.tile(target)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(target, replace(tile, terrain=Terrain.LAKE)),
        phase="cult_spades",
        spade_return="action",
        spade_actor=player,
        cult_spades=replace_at(state.cult_spades, player, 0),
        power_spade_tiles=(target,),
        spade_second=None,
        spade_topup=True,
        spade_require_all=False,
        active_player=player,
    )
    assert BuildDwelling(target) in listing(state)
    assert BuildDwelling(target, river=river) in listing(state)

    state = start(num_players=2, seed=1)
    player = state.order[0]
    start_position, target = _adjacent_empty_pair(state)[:2]
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.ALCHEMISTS,
            resources=Resources(coins=0, workers=50, priests=10),
            victory_points=10,
        ),
    )
    state = _neutral_scoring(
        replace(
            state,
            phase="cult_spades",
            spade_return="action",
            spade_actor=player,
            cult_spades=replace_at(state.cult_spades, player, 0),
            power_spade_tiles=(target,),
            spade_second=None,
            spade_topup=True,
            spade_require_all=False,
            active_player=player,
        )
    )
    assert TradeVpForCoin() in listing(state)
    after = GAME.apply(state, player, TradeVpForCoin()).state
    assert after.phase == "cult_spades"
    assert after.players[player].resources.coins == 1
    assert after.players[player].victory_points == 9


def test_cult_spade_turn_handoff_announces_the_next_budget() -> None:
    state = start(num_players=2, seed=1, rounds=1)
    spade_tile = ScoringTile(
        ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")
    )
    state = replace(
        state,
        phase="cult_spades",
        cult_spades=(2, 2),
        active_player=state.order[0],
        scoring=(spade_tile,),
        round=1,
    )
    transition = GAME.apply(state, state.order[0], SkipCultSpade())
    handoffs = [
        event
        for event in transition.events
        if event.kind == "cult_bonus" and event.data["player"] == state.order[1]
    ]
    assert len(handoffs) == 1
    assert handoffs[0].data["amount"] == 2
    assert transition.state.active_player == state.order[1]


def test_cult_spade_can_aim_at_a_chosen_terrain() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    spade_tile = ScoringTile(
        ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")
    )
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = replace(state, scoring=(spade_tile, priest_tile))
    state = replace(
        state,
        players=tuple(replace(player, cults=(9, 9, 9, 9)) for player in state.players),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    (decision,) = GAME.pending_decisions(state)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, UseCultSpade) and action.to is not None
    )
    after = GAME.apply(state, decision.player, action).state
    tile = after.board.tile(action.position)
    assert tile is not None and tile.terrain is action.to


def test_cult_spades_can_transform_a_tile_part_of_the_way() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    spade_tile = ScoringTile(
        ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")
    )
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = replace(state, scoring=(spade_tile, priest_tile))
    state = replace(
        state,
        players=tuple(replace(player, cults=(9, 9, 9, 9)) for player in state.players),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    assert state.phase == "cult_spades"
    (decision,) = GAME.pending_decisions(state)
    player = decision.player
    owner = state.players[player]
    state = replace(state, cult_spades=replace_at(state.cult_spades, player, 1))
    for action in listing(state):
        if not isinstance(action, UseCultSpade):
            continue
        tile = state.board.tile(action.position)
        assert tile is not None
        if spades_for(owner.profile, tile.terrain) > 1:
            break
    else:
        raise AssertionError("no reachable tile needs more than one spade")
    before = tile.terrain
    state = GAME.apply(state, player, action).state
    after = state.board.tile(action.position)
    assert after is not None
    assert after.terrain is terrain_toward(before, owner.home_terrain, 1)
    assert after.terrain is not owner.home_terrain
    assert state.cult_spades[player] == 0
