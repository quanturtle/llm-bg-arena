"""Unit tests for the Terra Mystica base game implementation."""

import asyncio
from dataclasses import replace

import pytest

from boardgames.arena.runner import play_match
from boardgames.core import (
    ConfigError,
    Event,
    IllegalActionError,
    NotationError,
    PlayerId,
    create_game,
    seats,
)
from boardgames.games.terra_mystica import (
    Action,
    AdvanceCult,
    AdvanceShipping,
    Board,
    BuildDwelling,
    Building,
    ChooseStrongholdPriests,
    Hex,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TakeTownTile,
    TerraMystica,
    TerraMysticaConfig,
    TerraMysticaState,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
    UseCultSpade,
)
from boardgames.games.terra_mystica.constants import (
    CULT_ORDER_STEPS,
    FACTION_BY_TYPE,
    FACTION_PROFILES,
    MAX_BUILDINGS,
    SCORING_TILES,
    STANDARD_TRADING_HOUSE_INCOME,
    TERRAIN_WHEEL,
    TOWN_SUPPLY,
    TOWN_TILES,
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    Income,
    Resources,
    ScoringAction,
    ScoringTile,
    Terrain,
)
from boardgames.games.terra_mystica.game import (
    end_round,
    income_for,
    initial_setup_queue,
)
from boardgames.games.terra_mystica.model import (
    PlayerState,
    advance_cult,
    building_cost,
    cult_limit,
    gain_power,
    income_with_power,
    replace_at,
    replace_player,
    settle_town,
    shipping_points,
    spade_cost,
    spades_for,
    spend_power,
    terrain_distance,
    terrain_toward,
    town_ready,
)
from boardgames.games.terra_mystica.scoring import (
    final_scores,
    largest_area,
    split_rank_points,
)
from boardgames.logs.replay import replay_match
from tests.arena.support import FakeClock, MemorySink, random_agents
from tests.invariants.playthrough import random_playthrough

GAME = TerraMystica()
P1, P2, P3 = seats(3)


def start(num_players: int = 2, seed: int = 1, rounds: int = 1) -> TerraMysticaState:
    return GAME.setup(
        TerraMysticaConfig(num_players=num_players, rounds=rounds), seed
    ).state


def listing(state: TerraMysticaState) -> tuple[Action, ...]:
    (decision,) = GAME.pending_decisions(state)
    actions = GAME.legal_actions(state, decision).listing(10_000)
    assert actions is not None
    return actions


def notations(state: TerraMysticaState) -> list[str]:
    return [GAME.format_action(action) for action in listing(state)]


def play(state: TerraMysticaState, notation: str) -> TerraMysticaState:
    (decision,) = GAME.pending_decisions(state)
    action = GAME.parse_action(notation)
    return GAME.apply(state, decision.player, action).state


def play_setup(state: TerraMysticaState) -> TerraMysticaState:
    while state.phase == "setup":
        state = play(state, notations(state)[0])
    return state


def with_resources(
    state: TerraMysticaState, player: PlayerId, **values: int
) -> TerraMysticaState:
    resources = replace(state.players[player].resources, **values)
    return replace_player(
        state, player, replace(state.players[player], resources=resources)
    )


# Setup --------------------------------------------------------------------


def test_config_validation() -> None:
    assert GAME.parse_config({}) == TerraMysticaConfig()
    for raw in ({"num_players": 1}, {"num_players": 6}, {"rounds": 0}, {"rounds": 7}):
        with pytest.raises(ConfigError):
            GAME.parse_config(raw)


def test_setup_assigns_distinct_factions_and_valid_starting_state() -> None:
    state = start(num_players=5, seed=7, rounds=2)
    factions = [player.faction for player in state.players]
    assert len(set(factions)) == 5
    assert len({player.home_terrain for player in state.players}) == 5
    for player in state.players:
        profile = FACTION_BY_TYPE[player.faction]
        assert player.victory_points == 20
        assert player.resources == profile.starting_resources
        assert player.resources.power == 12
        assert player.cults == profile.starting_cults
        assert len(player.cults) == 4
        assert player.shipping == profile.shipping_start
        assert player.digging == profile.digging_start


def test_faction_profiles_are_hashable_and_have_twelve_power() -> None:
    for profile in FACTION_PROFILES:
        assert hash(profile)
        assert profile.starting_resources.power == 12
        assert len(profile.starting_cults) == 4


def test_setup_asks_each_player_to_place_starting_dwellings() -> None:
    state = start(num_players=4, seed=3)
    expected = sum(player.profile.starting_dwellings for player in state.players)
    placements = 0
    while state.phase == "setup":
        assert GAME.pending_decisions(state)
        state = play(state, notations(state)[0])
        placements += 1
    assert placements == expected
    for seat in seats(4):
        assert state.board.count(seat, BuildingType.DWELLING) == (
            state.players[seat].profile.starting_dwellings
        )
    assert state.setup_queue == ()


def test_setup_queue_handles_nomads_and_chaos_magicians() -> None:
    players = (
        PlayerState(
            faction=FactionType.NOMADS,
            resources=FACTION_BY_TYPE[FactionType.NOMADS].starting_resources,
        ),
        PlayerState(
            faction=FactionType.CHAOS_MAGICIANS,
            resources=FACTION_BY_TYPE[FactionType.CHAOS_MAGICIANS].starting_resources,
        ),
        PlayerState(
            faction=FactionType.WITCHES,
            resources=FACTION_BY_TYPE[FactionType.WITCHES].starting_resources,
        ),
    )
    queue = initial_setup_queue((P1, P2, P3), players)
    assert queue.count(P1) == 3
    assert queue.count(P2) == 1
    assert queue.count(P3) == 2
    assert queue[-1] == P2
    assert queue == (P1, P3, P3, P1, P1, P2)


def test_starting_dwellings_must_be_on_home_terrain() -> None:
    state = start(num_players=2, seed=1)
    player = state.active_player
    home = state.players[player].home_terrain
    wrong = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is not home
    )
    with pytest.raises(IllegalActionError, match="home terrain"):
        GAME.apply(state, player, BuildDwelling(wrong))


# Actions ------------------------------------------------------------------


def test_build_dwelling_uses_an_adjacent_home_tile() -> None:
    state = play_setup(start(num_players=2, seed=1))
    player = state.active_player
    before = state.board.count(player, BuildingType.DWELLING)
    action = next(
        action for action in listing(state) if isinstance(action, BuildDwelling)
    )
    state = GAME.apply(state, player, action).state
    assert state.board.count(player, BuildingType.DWELLING) == before + 1
    tile = state.board.tile(action.position)
    assert tile is not None and tile.building is not None
    assert tile.building.owner == player


def test_shipping_crosses_a_fixed_river_tile() -> None:
    board = Board.base()
    for tile in board.tiles:
        if tile.is_land:
            continue
        land = [
            neighbour
            for neighbour in tile.position.neighbours()
            if (other := board.tile(neighbour)) is not None and other.is_land
        ]
        for start in land:
            direct = board.reachable_from(start, 0)
            shipped = board.reachable_from(start, 1)
            across = [
                neighbour
                for neighbour in land
                if neighbour != start and neighbour not in direct
            ]
            if across:
                assert across[0] in shipped
                return
    raise AssertionError("no river tile has land on both banks")


def test_build_dwelling_requires_adjacency() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    home = state.players[player].home_terrain
    reachable = set(state.board.reachable_land(player, state.players[player].shipping))
    target = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.terrain is home
        and tile.building is None
        and tile.position not in reachable
    )
    with pytest.raises(IllegalActionError, match="adjacent"):
        GAME.apply(state, player, BuildDwelling(target))


def test_transform_and_build_changes_terrain_and_pays_spades() -> None:
    state = play_setup(start(num_players=3, seed=5))
    player = state.active_player
    action = next(
        (
            action
            for action in listing(state)
            if isinstance(action, BuildDwelling)
            and (tile := state.board.tile(action.position)) is not None
            and tile.terrain is not state.players[player].home_terrain
        ),
        None,
    )
    if action is None:
        pytest.skip("no adjacent non-home tile in this setup")
    tile = state.board.tile(action.position)
    assert tile is not None
    spades = spades_for(state.players[player].profile, tile.terrain)
    assert spades > 0
    before = state.players[player].resources
    state = GAME.apply(state, player, action).state
    new_tile = state.board.tile(action.position)
    assert new_tile is not None
    assert new_tile.terrain is state.players[player].home_terrain
    assert state.players[player].resources.workers <= before.workers


def test_upgrade_dwelling_to_trading_house() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, coins=30, workers=10)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, UpgradeBuilding)
        and action.to is BuildingType.TRADING_HOUSE
    )
    state = GAME.apply(state, player, action).state
    tile = state.board.tile(action.position)
    assert tile is not None and tile.building is not None
    assert tile.building.type is BuildingType.TRADING_HOUSE


def test_send_priest_costs_a_priest_and_advances_cult() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, priests=1)
    before = state.players[player].cult(Cult.FIRE)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, SendPriest) and action.cult is Cult.FIRE
    )
    state = GAME.apply(state, player, action).state
    assert state.players[player].resources.priests == 0
    assert state.players[player].cult(Cult.FIRE) > before
    assert state.used_orders[(action.cult, action.order)] == player


def test_cult_order_spaces_are_shared() -> None:
    state = play_setup(start(num_players=2, seed=2))
    first = state.active_player
    second = next(seat for seat in seats(2) if seat != first)
    state = with_resources(state, first, priests=1)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, SendPriest)
        and action.cult is Cult.FIRE
        and action.order == 0
    )
    state = GAME.apply(state, first, action).state
    assert state.used_orders[(Cult.FIRE, 0)] == first
    state = with_resources(state, second, priests=1)
    state = replace(state, active_player=second)
    assert not any(
        isinstance(action, SendPriest)
        and action.cult is Cult.FIRE
        and action.order == 0
        for action in listing(state)
    )


def test_standard_rule_tables_match_the_base_game() -> None:
    assert CULT_ORDER_STEPS[0] == 3
    assert all(steps == 2 for steps in CULT_ORDER_STEPS[1:])
    assert [shipping_points(level, 0) for level in (1, 2, 3)] == [2, 3, 4]
    assert shipping_points(2, 1) == 2
    assert FACTION_BY_TYPE[FactionType.WITCHES].base_income.workers == 1
    assert FACTION_BY_TYPE[FactionType.ENGINEERS].base_income.workers == 0
    assert FACTION_BY_TYPE[FactionType.SWARMLINGS].base_income.workers == 2
    state = start(num_players=2, seed=1, rounds=1)
    for faction, workers in (
        (FactionType.WITCHES, 1),
        (FactionType.ENGINEERS, 0),
        (FactionType.SWARMLINGS, 2),
    ):
        owner = replace(state.players[0], faction=faction)
        assert income_for(state.board, PlayerId(0), owner).workers == workers
    trading = tuple(income.power for income in STANDARD_TRADING_HOUSE_INCOME)
    assert trading == (1, 2, 4, 6)


def test_advance_cult_costs_a_priest() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, priests=1)
    action = next(
        action for action in listing(state) if isinstance(action, AdvanceCult)
    )
    before = state.players[player].cult(action.cult)
    state = GAME.apply(state, player, action).state
    assert state.players[player].resources.priests == 0
    assert state.players[player].cult(action.cult) == before + 1


def test_cult_space_ten_requires_a_key() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    owner = state.players[player]
    owner = owner.with_cult(Cult.EARTH, 9)
    owner = replace(owner, resources=replace(owner.resources, priests=1))
    state = replace_player(state, player, owner)
    assert cult_limit(state.players[player]) == 9
    assert not any(
        isinstance(action, AdvanceCult) and action.cult is Cult.EARTH
        for action in listing(state)
    )
    assert any(
        isinstance(action, SendPriest) and action.cult is Cult.EARTH
        for action in listing(state)
    )
    owner = replace(state.players[player], keys=1)
    state = replace_player(state, player, owner)
    assert cult_limit(state.players[player]) == 10
    assert any(
        action.cult is Cult.EARTH
        for action in listing(state)
        if isinstance(action, AdvanceCult)
    )


def test_second_player_cannot_enter_an_occupied_cult_top() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    other = next(seat for seat in seats(2) if seat != player)
    owner = state.players[player].with_cult(Cult.FIRE, 9)
    owner = replace(owner, keys=1, resources=replace(owner.resources, priests=1))
    state = replace_player(state, player, owner)
    other_owner = state.players[other].with_cult(Cult.FIRE, 10)
    state = replace_player(state, other, other_owner)
    assert not any(
        isinstance(action, AdvanceCult) and action.cult is Cult.FIRE
        for action in listing(state)
    )
    assert any(
        isinstance(action, SendPriest) and action.cult is Cult.FIRE
        for action in listing(state)
    )


def test_priest_can_block_an_order_space_on_a_full_track() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    owner = state.players[player].with_cult(Cult.EARTH, 9)
    owner = replace(owner, resources=replace(owner.resources, priests=1))
    state = replace_player(state, player, owner)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, SendPriest) and action.cult is Cult.EARTH
    )
    after = GAME.apply(state, player, action).state
    assert after.players[player].cult(Cult.EARTH) == 9
    assert after.used_orders[(Cult.EARTH, action.order)] == player
    assert after.players[player].resources.priests == 0


def test_power_actions_spend_bowl_three_power() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, power1=0, power2=0, power3=12)
    action = next(
        action for action in listing(state) if isinstance(action, PowerAction)
    )
    state = GAME.apply(state, player, action).state
    assert state.players[player].resources.power3 < 12
    assert action.kind in state.used_power_actions


def test_pass_awards_starting_player_and_advances_round() -> None:
    state = play_setup(start(num_players=3, seed=4, rounds=2))
    first_passer = state.active_player
    while state.round == 1 and state.phase == "action":
        state = play(state, "pass")
    assert state.round == 2
    assert state.order[0] == first_passer
    assert state.phase == "action"


def test_game_ends_after_final_round_with_scores() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=1))
    while not GAME.is_terminal(state):
        state = play(state, "pass")
    assert GAME.pending_decisions(state) == ()
    scores = GAME.scores(state)
    assert len(scores.points) == 2
    assert all(points >= 0 for points in scores.points.values())
    assert scores.breakdown


def test_final_scores_are_computed_from_board_and_resources() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=1))
    while not GAME.is_terminal(state):
        state = play(state, "pass")
    final = final_scores(state)
    for seat in seats(2):
        points, breakdown = final[seat]
        assert points == sum(breakdown.values())


# Notation, observation and registration -----------------------------------


def test_leftover_bowl_three_power_scores_as_coins() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state = with_resources(
        state,
        player,
        coins=0,
        workers=0,
        priests=0,
        power1=0,
        power2=0,
        power3=9,
    )
    assert final_scores(state)[player][1]["resources"] == 3


def test_notation_round_trips_for_every_legal_action() -> None:
    state = start(num_players=2, seed=1)
    while not GAME.is_terminal(state):
        for action in listing(state):
            text = GAME.format_action(action)
            assert GAME.parse_action(text) == action
        state = play(state, notations(state)[0])


def test_river_notation_round_trips() -> None:
    river = Hex(1, 1)
    build = BuildDwelling(Hex(0, 0), river=river)
    assert GAME.format_action(build) == "build 0,0 river 1,1"
    assert GAME.parse_action("build 0,0 river 1,1") == build
    upgrade = UpgradeBuilding(Hex(1, 0), BuildingType.TEMPLE, river=river)
    assert GAME.format_action(upgrade) == "upgrade 1,0 temple river 1,1"
    assert GAME.parse_action("upgrade 1,0 temple river 1,1") == upgrade


def test_new_action_notation_round_trips() -> None:
    actions = (
        TakeTownTile(0),
        TradeVpForCoin(),
        TradeCoinsForVp(),
        ChooseStrongholdPriests(2),
        TransformTerrain(Hex(0, 0), Terrain.LAKE),
        UseCultSpade(Hex(0, 0), Terrain.LAKE),
        PowerAction("spade"),
        PowerAction("double_spade"),
    )
    for action in actions:
        assert GAME.parse_action(GAME.format_action(action)) == action


def test_parse_rejects_bad_notation() -> None:
    for text in ("", "build", "build x,y", "upgrade 0,0 castle", "priest sun 0"):
        with pytest.raises(NotationError):
            GAME.parse_action(text)


def test_observation_is_public_and_renders() -> None:
    state = start(num_players=2, seed=1)
    spectator = GAME.observe(state, None)
    first = GAME.observe(state, P1)
    assert spectator.data["players"] == first.data["players"]
    assert spectator.data["board"] == first.data["board"]
    text = GAME.render_text(spectator)
    assert "Terra Mystica" not in text
    assert "Board:" in text
    assert "Round scoring:" in text
    assert "Legend:" in text


def test_observation_and_round_event_show_cult_bonuses() -> None:
    state = start(num_players=2, seed=1)
    observation = GAME.observe(state, None)
    bonuses = observation.data["scoring_bonuses"]
    assert isinstance(bonuses, list)
    assert len(bonuses) == 1
    assert isinstance(bonuses[0], dict)
    assert set(bonuses[0]) == {"cult", "per", "reward", "amount"}

    round_events: list[Event] = []
    while state.phase == "setup":
        (decision,) = GAME.pending_decisions(state)
        transition = GAME.apply(state, decision.player, listing(state)[0])
        state = transition.state
        round_events.extend(
            event for event in transition.events if event.kind == "round_started"
        )
    assert round_events
    assert "bonus" in round_events[0].data


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
    before = state.players[player].resources
    after = GAME.apply(state, player, UseCultSpade(target)).state
    tile = after.board.tile(target)
    assert tile is not None and tile.terrain is Terrain.MOUNTAIN
    assert after.players[player].resources.workers == before.workers - 2


def test_action_phase_spades_use_a_single_tile_then_one_extra() -> None:
    state, player, _start, first, second = _action_spade_state(FactionType.WITCHES, 2)
    board = state.board
    for position in (first, second):
        tile = board.tile(position)
        assert tile is not None
        board = board.replace_tile(position, replace(tile, terrain=Terrain.LAKE))
    state = replace(state, board=board)
    actions = listing(state)
    assert not any(
        action.to is not None for action in actions if isinstance(action, UseCultSpade)
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


def test_priest_supply_caps_cult_bonuses() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=2))
    priest_tile = ScoringTile(
        ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")
    )
    state = replace(state, scoring=(priest_tile, priest_tile))
    first, second = state.order
    state = replace(
        state,
        used_orders={(Cult.FIRE, 0): first, (Cult.WATER, 0): second},
        players=tuple(
            replace(
                player,
                cults=(9, 9, 9, 9),
                resources=replace(player.resources, priests=6),
            )
            for player in state.players
        ),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    assert state.round == 2
    assert all(player.resources.priests == 6 for player in state.players)


def test_alchemists_trade_vp_and_coins_without_ending_the_turn() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.ALCHEMISTS,
            victory_points=20,
            resources=Resources(coins=4, workers=5, priests=1),
        ),
    )
    assert TradeVpForCoin() in listing(state)
    assert TradeCoinsForVp() in listing(state)
    state = GAME.apply(state, player, TradeVpForCoin()).state
    owner = state.players[player]
    assert owner.victory_points == 19 and owner.resources.coins == 5
    assert state.phase == "action" and state.active_player == player
    state = GAME.apply(state, player, TradeCoinsForVp()).state
    owner = state.players[player]
    assert owner.victory_points == 20 and owner.resources.coins == 3


def test_action_json_has_a_type_tag() -> None:
    action = BuildDwelling(Hex(0, 0))
    assert GAME.action_json(action)["type"] == "build_dwelling"
    assert GAME.action_json(Pass()) == {"type": "pass"}


def test_registered_under_its_id() -> None:
    assert isinstance(create_game("terra_mystica"), TerraMystica)


# Helpers and lower-level rules --------------------------------------------


def test_power_bowls_keep_twelve_tokens_in_the_cycle() -> None:
    resources = Resources(power1=5, power2=7)
    assert resources.power == 12
    gained = gain_power(resources, 10)
    assert gained.power == 12
    assert (gained.power1, gained.power2, gained.power3) == (0, 7, 5)
    spent = spend_power(gained, 3)
    assert spent is not None
    assert (spent.power1, spent.power2, spent.power3) == (3, 7, 2)
    assert spend_power(spent, 99) is None


def test_income_includes_power_and_resources() -> None:
    resources = Resources(coins=1, workers=1, priests=1, power1=5, power2=7)
    updated = income_with_power(
        resources, Income(coins=2, workers=3, priests=4, power=2)
    )
    assert updated.coins == 3
    assert updated.workers == 4
    assert updated.priests == 5
    assert updated.power == 12


def test_spade_costs_use_workers_and_darklings_use_priests() -> None:
    witches = FACTION_BY_TYPE[FactionType.WITCHES]
    assert spades_for(witches, witches.home_terrain) == 0
    other = next(
        terrain for terrain in TERRAIN_WHEEL if terrain is not witches.home_terrain
    )
    assert spades_for(witches, other) >= 1
    assert spade_cost(witches, 0, 2).workers == 6
    assert spade_cost(witches, 2, 2).workers == 2
    darklings = FACTION_BY_TYPE[
        next(faction for faction in FACTION_BY_TYPE if faction.value == "darklings")
    ]
    assert spade_cost(darklings, 0, 2).priests == 2


def test_advance_cult_grants_power_at_thresholds_and_spends_a_key() -> None:
    owner = PlayerState(
        faction=next(iter(FACTION_BY_TYPE)),
        resources=Resources(power1=5, power2=7),
        cults=(2, 0, 0, 0),
    )
    advanced, gained = advance_cult(owner, Cult.FIRE, 3)
    assert advanced.cult(Cult.FIRE) == 5
    assert gained == 3
    owner = replace(owner, cults=(9, 0, 0, 0), keys=1)
    advanced, gained = advance_cult(owner, Cult.FIRE, 3)
    assert advanced.cult(Cult.FIRE) == 10
    assert advanced.keys == 0
    assert gained == 3


def action_state(
    state: TerraMysticaState, player: PlayerId, *buildings: tuple[Hex, BuildingType]
) -> TerraMysticaState:
    board = state.board
    for position, building_type in buildings:
        board = board.place(position, Building(building_type, player))
    state = replace_player(
        state,
        player,
        replace(state.players[player], resources=Resources(coins=50, workers=50)),
    )
    return replace(
        state,
        board=board,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
        pass_order=(),
        round=1,
    )


def with_witches_dwelling(
    state: TerraMysticaState, player: PlayerId
) -> tuple[TerraMysticaState, Hex]:
    start_position, target = next(
        (tile.position, neighbour)
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
        for neighbour in tile.position.neighbours()
        if (other := state.board.tile(neighbour)) is not None
        and other.is_land
        and other.building is None
    )
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.WITCHES)
    )
    return state, target


def empty_land_tiles(state: TerraMysticaState) -> list[Hex]:
    return [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    ]


def test_engineers_eighth_dwelling_pays_six_workers() -> None:
    state = start(num_players=2, seed=1)
    positions = empty_land_tiles(state)[:8]
    board = state.board
    for position in positions:
        board = board.place(position, Building(BuildingType.DWELLING, P1))
    owner = replace(state.players[P1], faction=FactionType.ENGINEERS)
    assert income_for(board, P1, owner).workers == 6


def test_spade_round_tile_never_lands_in_rounds_five_or_six() -> None:
    missing = 0
    for seed in range(200):
        state = start(num_players=2, seed=seed, rounds=6)
        positions = [
            index
            for index, tile in enumerate(state.scoring)
            if tile.action is ScoringAction.SPADE
        ]
        assert len(positions) <= 1
        if positions:
            assert positions[0] < 4
        else:
            missing += 1
    assert missing > 0


def test_shipping_is_not_listed_at_the_maximum() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    owner = replace(
        state.players[player],
        faction=FactionType.WITCHES,
        shipping=FACTION_BY_TYPE[FactionType.WITCHES].shipping_max,
        resources=Resources(coins=20, workers=5, priests=3),
    )
    state = replace_player(
        state,
        player,
        owner,
    )
    state = replace(
        state,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
        pass_order=(),
        round=1,
    )
    assert AdvanceShipping() not in listing(state)


def test_mermaids_earn_two_points_on_their_first_shipping_step() -> None:
    state = start(num_players=2, seed=1, rounds=1)
    player = state.order[0]
    state = replace(
        state,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
        pass_order=(),
        round=1,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
    )
    owner = replace(
        state.players[player],
        faction=FactionType.MERMAIDS,
        shipping=1,
        resources=Resources(coins=20, workers=5, priests=3),
    )
    state = replace_player(state, player, owner)
    before = state.players[player].victory_points
    after = GAME.apply(state, player, AdvanceShipping()).state
    assert after.players[player].shipping == 2
    assert after.players[player].victory_points == before + 2


def test_two_round_tiles_use_the_combined_stronghold_or_sanctuary_action() -> None:
    combined = [
        tile
        for tile in SCORING_TILES
        if tile.action is ScoringAction.STRONGHOLD_OR_SANCTUARY
    ]
    assert len(combined) == 2


@pytest.mark.parametrize(
    ("target", "source"),
    [
        (BuildingType.STRONGHOLD, BuildingType.TRADING_HOUSE),
        (BuildingType.SANCTUARY, BuildingType.TEMPLE),
    ],
)
def test_both_five_vp_tiles_score_strongholds_or_sanctuaries(
    target: BuildingType, source: BuildingType
) -> None:
    state = start(num_players=2, seed=1, rounds=1)
    player = state.order[0]
    position = empty_land_tiles(state)[0]
    state = action_state(state, player, (position, source))
    state = replace(
        state,
        scoring=(
            ScoringTile(
                ScoringAction.STRONGHOLD_OR_SANCTUARY,
                CultBonus(Cult.AIR, 2, "workers"),
            ),
        ),
    )
    before = state.players[player].victory_points
    after = GAME.apply(state, player, UpgradeBuilding(position, target)).state
    assert after.players[player].victory_points == before + 5


def test_ninth_dwelling_is_explained_by_supply() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = empty_land_tiles(state)
    board = state.board
    for position in positions[:8]:
        board = board.place(position, Building(BuildingType.DWELLING, player))
    state = replace(
        state,
        board=board,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
    )
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert space.explain(BuildDwelling(positions[8])) == "You have no dwellings left."


def test_observation_and_text_show_passes_power_actions_and_cult_spades() -> None:
    state = start(num_players=2, seed=1, rounds=1)
    state = replace(
        state,
        passed=frozenset({PlayerId(1)}),
        pass_order=(PlayerId(1),),
        used_power_actions=frozenset({"coins"}),
    )
    observation = GAME.observe(state, None)
    data = observation.data
    assert data["pass_order"] == [1]
    assert data["used_power_actions"] == ["coins"]
    assert "home_terrains" not in data
    assert "active_cult_spades" not in data
    players = data["players"]
    assert isinstance(players, list)
    assert all("home_terrain" in player for player in players)
    text = GAME.render_text(observation)
    assert "Passed in order:" in text
    assert "Power actions used this round: coins." in text
    assert "home " in text
    assert "cult-bonus spade" not in text
    spade_state = replace(
        state,
        phase="cult_spades",
        cult_spades=(2, 2),
        active_player=PlayerId(0),
    )
    spade_text = GAME.render_text(GAME.observe(spade_state, None))
    assert "P1 has 2 cult-bonus spade(s)." in spade_text


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


def test_towns_require_power_and_are_marked_once() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    position = next(
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
        >= 3
    )
    types = (
        BuildingType.STRONGHOLD,
        BuildingType.TRADING_HOUSE,
        BuildingType.TEMPLE,
        BuildingType.DWELLING,
    )
    neighbours = [
        neighbour
        for neighbour in position.neighbours()
        if (tile := state.board.tile(neighbour)) is not None and tile.is_land
    ][:3]
    state = action_state(
        state,
        player,
        (position, types[0]),
        *zip(neighbours, types[1:], strict=True),
    )
    component = state.board.connected(position, player)
    assert town_ready(state.board, component)
    board, founded = settle_town(state.board, position, player, towns_left=TOWN_SUPPLY)
    assert founded
    for hex_position in component:
        tile = board.tile(hex_position)
        assert tile is not None and tile.building is not None
        assert tile.building.in_town
    assert not settle_town(board, position, player, towns_left=TOWN_SUPPLY)[1]
    weak = Board.base()
    weak_positions = [Hex(q, 0) for q in range(4)]
    for weak_position, weak_type in zip(
        weak_positions,
        (
            BuildingType.TRADING_HOUSE,
            BuildingType.TRADING_HOUSE,
            BuildingType.DWELLING,
            BuildingType.DWELLING,
        ),
        strict=True,
    ):
        weak = weak.place(weak_position, Building(weak_type, player))
    weak_component = weak.connected(weak_positions[0], player)
    assert not town_ready(weak, weak_component)
    assert not settle_town(weak, weak_positions[0], player, towns_left=TOWN_SUPPLY)[1]


def test_town_supply_stops_after_ten_towns() -> None:
    board = Board.base()
    player = P1
    position = next(tile.position for tile in board.tiles if tile.is_land)
    assert not settle_town(board, position, player, towns_left=0)[1]


def _town_gap_layout(board: Board, *, river_between: bool) -> tuple[Hex, Hex, Hex, Hex]:
    """Two adjacent pairs, two spaces apart, with a land or river gap."""

    def land(position: Hex) -> bool:
        tile = board.tile(position)
        return tile is not None and tile.is_land

    for a in (tile.position for tile in board.tiles if tile.is_land):
        for a2 in (neighbour for neighbour in a.neighbours() if land(neighbour)):
            for b in (tile.position for tile in board.tiles if tile.is_land):
                if a.distance(b) != 2 or b in a2.neighbours() or b == a2:
                    continue
                middle = [
                    neighbour
                    for neighbour in a.neighbours()
                    if neighbour in b.neighbours()
                ]
                is_river = all(
                    not land(neighbour) and board.tile(neighbour) is not None
                    for neighbour in middle
                )
                if is_river is not river_between:
                    continue
                for b2 in (
                    neighbour for neighbour in b.neighbours() if land(neighbour)
                ):
                    if b2 in (a, a2) or b2 in a.neighbours() or b2 in a2.neighbours():
                        continue
                    return a, a2, b, b2
    raise AssertionError("no two-group layout found")


def _town_gap_board(river_between: bool) -> tuple[Board, Hex, Hex | None]:
    board = Board.base()
    a, a2, b, b2 = _town_gap_layout(board, river_between=river_between)
    for position, kind in (
        (a, BuildingType.STRONGHOLD),
        (a2, BuildingType.TRADING_HOUSE),
        (b, BuildingType.TEMPLE),
        (b2, BuildingType.DWELLING),
    ):
        board = board.place(position, Building(kind, P1))
    river = next(
        neighbour for neighbour in a.neighbours() if neighbour in b.neighbours()
    )
    return board, b2, river


def test_towns_ignore_indirect_adjacency() -> None:
    board, position, _river = _town_gap_board(river_between=False)
    assert not settle_town(board, position, P1, towns_left=TOWN_SUPPLY)[1]


def test_mermaids_may_join_one_river_space_for_a_town() -> None:
    board, position, river = _town_gap_board(river_between=True)
    assert settle_town(board, position, P1, towns_left=TOWN_SUPPLY, river=river)[1]


def _mermaid_gap_state(
    *, weak: bool = False
) -> tuple[TerraMysticaState, PlayerId, Hex, Hex]:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    board = Board.base()
    a, a2, b, b2 = _town_gap_layout(board, river_between=True)
    river = next(
        neighbour for neighbour in a.neighbours() if neighbour in b.neighbours()
    )
    buildings = [(a, BuildingType.STRONGHOLD)]
    if not weak:
        buildings.append((a2, BuildingType.TRADING_HOUSE))
    buildings.append((b, BuildingType.TEMPLE))
    for position, kind in buildings:
        board = board.place(position, Building(kind, player))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.MERMAIDS,
            resources=Resources(coins=50, workers=50, priests=5, power1=5, power2=7),
            shipping=1,
        ),
    )
    state = _neutral_scoring(
        replace(
            state,
            board=board,
            phase="action",
            active_player=player,
            passed=frozenset(),
            pass_order=(),
            setup_queue=(),
            round=1,
        )
    )
    return state, player, b2, river


def test_mermaids_may_join_the_river_town() -> None:
    state, player, target, river = _mermaid_gap_state()
    assert BuildDwelling(target) in listing(state)
    assert BuildDwelling(target, river=river) in listing(state)

    separate = GAME.apply(state, player, BuildDwelling(target)).state
    joined = GAME.apply(state, player, BuildDwelling(target, river=river)).state
    assert joined.towns == 1
    assert joined.players[player].keys == 1
    assert separate.towns == 0
    assert separate.players[player].keys == 0
    tile = separate.board.tile(target)
    assert tile is not None and tile.building is not None
    assert not tile.building.in_town


def test_mermaids_only_list_join_when_it_changes_the_town() -> None:
    state, _player, target, river = _mermaid_gap_state(weak=True)
    assert BuildDwelling(target) in listing(state)
    assert BuildDwelling(target, river=river) not in listing(state)


def test_only_mermaids_may_join_the_river_town() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    target = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    river = next(tile.position for tile in state.board.tiles if not tile.is_land)
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert "Only the Mermaids" in space.explain(BuildDwelling(target, river=river))

    with_building = action_state(state, player, (target, BuildingType.DWELLING))
    (decision,) = GAME.pending_decisions(with_building)
    space = GAME.legal_actions(with_building, decision)
    assert "Only the Mermaids" in space.explain(
        UpgradeBuilding(target, BuildingType.TRADING_HOUSE, river=river)
    )


def test_dwarves_and_fakirs_reach_across_two_and_three_spaces() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    occupied = state.board.occupied(player)[0]
    two_away = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and occupied.distance(tile.position) == 2
        and tile.position not in state.board.reachable_from(occupied, 0)
    )
    assert two_away in state.board.reachable_from(occupied, 0, 2)
    three_away = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and occupied.distance(tile.position) == 3
        and tile.position not in state.board.reachable_from(occupied, 0)
    )
    assert three_away not in state.board.reachable_from(occupied, 0, 2)
    assert three_away in state.board.reachable_from(occupied, 0, 3)


def _neutral_scoring(state: TerraMysticaState) -> TerraMysticaState:
    tile = ScoringTile(ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "priests"))
    return replace(state, scoring=(tile, tile))


def _terrain_target(
    state: TerraMysticaState, terrain: Terrain, distance: int
) -> tuple[Hex, Hex]:
    starts = [tile.position for tile in state.board.tiles if tile.is_land]
    targets = [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is terrain
    ]
    for start in starts:
        for target in targets:
            if start.distance(target) == distance:
                return start, target
    raise AssertionError(f"no {terrain.value} tile {distance} from a start")


def _same_terrain_pair(
    state: TerraMysticaState, terrain: Terrain, distance: int
) -> tuple[Hex, Hex]:
    positions = [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is terrain
    ]
    for start in positions:
        for target in positions:
            if start.distance(target) == distance:
                return start, target
    raise AssertionError(f"no {terrain.value} pair {distance} apart")


def test_dwarves_tunnel_costs_two_workers_and_scores_four_points() -> None:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.DWARVES),
    )
    start_position, target = _same_terrain_pair(state, Terrain.MOUNTAIN, 2)
    state = _neutral_scoring(
        action_state(state, player, (start_position, BuildingType.DWELLING))
    )
    before = state.players[player]
    after = GAME.apply(state, player, BuildDwelling(target)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.workers - after.players[player].resources.workers == 3


def test_transform_can_stop_at_another_terrain() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state, target = with_witches_dwelling(state, player)
    tile = state.board.tile(target)
    assert tile is not None
    to = next(
        terrain
        for terrain in TERRAIN_WHEEL
        if terrain is not tile.terrain
        and terrain is not state.players[player].home_terrain
        and terrain_distance(tile.terrain, terrain) == 1
    )
    action = TransformTerrain(target, to)
    assert action in listing(state)
    after = GAME.apply(state, player, action).state
    changed = after.board.tile(target)
    assert changed is not None and changed.terrain is to


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


def test_dwarves_can_tunnel_to_transform_without_building() -> None:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.DWARVES),
    )
    start_position, target = _terrain_target(state, Terrain.FOREST, 2)
    state = _neutral_scoring(
        action_state(state, player, (start_position, BuildingType.DWELLING))
    )
    before = state.players[player]
    tile = state.board.tile(target)
    assert tile is not None
    spades = spades_for(before.profile, tile.terrain)
    expected_workers = spade_cost(before.profile, before.digging, spades).workers + 2
    after = GAME.apply(state, player, TransformTerrain(target)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert (
        before.resources.workers - after.players[player].resources.workers
        == expected_workers
    )


def test_a_dwarves_stronghold_makes_tunneling_cheaper() -> None:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.DWARVES),
    )
    start_position, target = _same_terrain_pair(state, Terrain.MOUNTAIN, 2)
    state = _neutral_scoring(
        action_state(state, player, (start_position, BuildingType.STRONGHOLD))
    )
    before = state.players[player]
    after = GAME.apply(state, player, BuildDwelling(target)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.workers - after.players[player].resources.workers == 2


def _fakir_state() -> tuple[TerraMysticaState, PlayerId]:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.FAKIRS),
    )
    return state, player


def test_fakirs_flight_costs_a_priest() -> None:
    state, player = _fakir_state()
    start_position, two_away = _terrain_target(state, Terrain.DESERT, 2)
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = with_resources(state, player, priests=5)
    state = _neutral_scoring(state)
    before = state.players[player]
    after = GAME.apply(state, player, BuildDwelling(two_away)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.priests - after.players[player].resources.priests == 1


def test_a_fakirs_stronghold_extends_flight_range() -> None:
    state, player = _fakir_state()
    start_position, three_away = _terrain_target(state, Terrain.DESERT, 3)
    without_stronghold = action_state(
        state, player, (start_position, BuildingType.DWELLING)
    )
    assert BuildDwelling(three_away) not in listing(without_stronghold)

    with_stronghold = action_state(
        state, player, (start_position, BuildingType.STRONGHOLD)
    )
    with_stronghold = with_resources(with_stronghold, player, priests=5)
    with_stronghold = _neutral_scoring(with_stronghold)
    before = with_stronghold.players[player]
    after = GAME.apply(with_stronghold, player, BuildDwelling(three_away)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.priests - after.players[player].resources.priests == 1


def test_dwarves_area_scoring_connects_through_their_reach() -> None:
    board = Board.base()
    player = P1
    positions = [tile.position for tile in board.tiles if tile.is_land]
    start = positions[0]
    other = next(position for position in positions if start.distance(position) == 2)
    board = board.place(start, Building(BuildingType.DWELLING, player))
    board = board.place(other, Building(BuildingType.DWELLING, player))
    assert largest_area(board, player, shipping=0, reach=0) == 1
    assert largest_area(board, player, shipping=0, reach=2) == 2


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


def test_town_upgrade_awards_points_key_and_round_tile_vp() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = [Hex(q, 0) for q in range(4)]
    state = action_state(
        state,
        player,
        *zip(
            positions,
            (
                BuildingType.TRADING_HOUSE,
                BuildingType.TRADING_HOUSE,
                BuildingType.DWELLING,
                BuildingType.DWELLING,
            ),
            strict=True,
        ),
    )
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.WITCHES)
    )
    state = replace(
        state,
        scoring=(ScoringTile(ScoringAction.TOWN, CultBonus(Cult.EARTH, 4, "spades")),),
    )
    before = state.players[player].victory_points
    state = GAME.apply(
        state, player, UpgradeBuilding(positions[3], BuildingType.TRADING_HOUSE)
    ).state
    assert state.phase == "town_choice"
    state = GAME.apply(state, player, TakeTownTile(0)).state
    after = state.players[player]
    assert after.victory_points - before == 15
    assert after.keys == 1
    return


def _stronghold_state(
    faction: FactionType,
) -> tuple[TerraMysticaState, PlayerId, Hex]:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=faction),
    )
    state = action_state(state, player, (position, BuildingType.TRADING_HOUSE))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            resources=Resources(coins=50, workers=50, priests=4, power1=5, power2=7),
        ),
    )
    return _neutral_scoring(state), player, position


def test_stronghold_one_time_rewards() -> None:
    state, player, position = _stronghold_state(FactionType.CULTISTS)
    before = state.players[player].victory_points
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.players[player].victory_points - before == 7

    state, player, position = _stronghold_state(FactionType.ALCHEMISTS)
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    resources = after.players[player].resources
    assert (resources.power1, resources.power2, resources.power3) == (0, 5, 7)

    state, player, position = _stronghold_state(FactionType.MERMAIDS)
    state = replace_player(state, player, replace(state.players[player], shipping=1))
    before_player = state.players[player]
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.players[player].shipping == 2
    assert after.players[player].victory_points == before_player.victory_points + 2

    state, player, position = _stronghold_state(FactionType.MERMAIDS)
    state = replace_player(state, player, replace(state.players[player], shipping=5))
    before_player = state.players[player]
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.players[player].shipping == 5
    assert after.players[player].victory_points == before_player.victory_points


def test_halfling_and_darkling_stronghold_rewards_need_a_choice() -> None:
    state, player, position = _stronghold_state(FactionType.HALFLINGS)
    before = state.players[player].victory_points
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.phase == "cult_spades"
    assert after.cult_spades[player] == 3
    assert after.players[player].victory_points - before == 3
    after = GAME.apply(after, player, SkipCultSpade()).state
    assert after.phase == "action"

    state, player, position = _stronghold_state(FactionType.DARKLINGS)
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.phase == "stronghold_convert"
    before_resources = after.players[player].resources
    after = GAME.apply(after, player, ChooseStrongholdPriests(3)).state
    assert after.phase == "action"
    resources = after.players[player].resources
    assert resources.workers == before_resources.workers - 3
    assert resources.priests == before_resources.priests + 3


def test_town_tile_choice_awards_its_reward() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = [Hex(q, 0) for q in range(4)]
    state = _neutral_scoring(state)
    state = action_state(
        state,
        player,
        *zip(
            positions,
            (
                BuildingType.TRADING_HOUSE,
                BuildingType.TRADING_HOUSE,
                BuildingType.DWELLING,
                BuildingType.DWELLING,
            ),
            strict=True,
        ),
    )
    state = GAME.apply(
        state, player, UpgradeBuilding(positions[3], BuildingType.TRADING_HOUSE)
    ).state
    assert state.phase == "town_choice"
    assert {
        action for action in listing(state) if isinstance(action, TakeTownTile)
    } == {TakeTownTile(index) for index in range(len(TOWN_TILES))}
    before = state.players[player]
    state = GAME.apply(state, player, TakeTownTile(2)).state
    after = state.players[player]
    assert state.town_tiles[2] == 1
    assert after.victory_points - before.victory_points == TOWN_TILES[2].victory_points
    assert after.resources.priests == before.resources.priests + 1


def test_dwelling_round_tile_scores_through_apply() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state, target = with_witches_dwelling(state, player)
    state = replace(
        state,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
    )
    before = state.players[player].victory_points
    state = GAME.apply(state, player, BuildDwelling(target)).state
    assert state.players[player].victory_points - before == 2
    return


def test_trading_house_round_tile_scores_through_apply() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state, target = with_witches_dwelling(state, player)
    state = GAME.apply(state, player, BuildDwelling(target)).state
    state = replace(
        state,
        active_player=player,
        scoring=(
            ScoringTile(ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")),
        ),
    )
    before = state.players[player].victory_points
    upgraded = GAME.apply(
        state, player, UpgradeBuilding(target, BuildingType.TRADING_HOUSE)
    ).state.players[player]
    assert upgraded.victory_points - before == 3
    return


def test_spade_round_tile_scores_through_transform() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    home = FACTION_BY_TYPE[FactionType.WITCHES].home_terrain
    start_position, target = next(
        (tile.position, neighbour)
        for tile in state.board.tiles
        if tile.is_land and tile.building is None and tile.terrain is not home
        for neighbour in tile.position.neighbours()
        if (other := state.board.tile(neighbour)) is not None
        and other.is_land
        and other.building is None
        and other.terrain is not home
    )
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.WITCHES)
    )
    state = replace(
        state,
        scoring=(ScoringTile(ScoringAction.SPADE, CultBonus(Cult.EARTH, 1, "coins")),),
    )
    tile = state.board.tile(target)
    assert tile is not None
    spades = spades_for(state.players[player].profile, tile.terrain)
    before = state.players[player].victory_points
    after = GAME.apply(state, player, TransformTerrain(target)).state
    assert after.players[player].victory_points - before == spades * 2
    return


def test_trading_house_discount_is_applied_by_upgrade() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    other = next(seat for seat in seats(2) if seat != player)
    position = Hex(0, 0)
    neighbour = position.neighbours()[0]
    state = action_state(state, player, (position, BuildingType.DWELLING))
    board = state.board.place(neighbour, Building(BuildingType.DWELLING, other))
    state = replace(state, board=board)
    before = state.players[player].resources.coins
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.TRADING_HOUSE)
    ).state.players[player]
    assert before - after.resources.coins == 3
    return


def test_standard_trading_house_and_temple_income() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    position = Hex(0, 0)
    state = action_state(
        state,
        player,
        (position, BuildingType.TRADING_HOUSE),
        (position.neighbours()[0], BuildingType.TEMPLE),
    )
    owner = replace(state.players[player], faction=FactionType.WITCHES)
    income = income_for(state.board, player, owner)
    assert (income.coins, income.power, income.priests) == (2, 1, 1)
    return


def test_final_majorities_split_ties_and_convert_resources() -> None:
    awards = split_rank_points([(P1, 5), (P2, 5), (P3, 3)], (8, 4, 2))
    assert awards == {P1: 6, P2: 6, P3: 2}
    state = start(num_players=2, seed=1, rounds=1)
    owner = replace(
        state.players[P1],
        faction=FactionType.ALCHEMISTS,
        resources=Resources(coins=5),
        victory_points=0,
        cults=(0, 0, 0, 0),
    )
    state = replace_player(state, P1, owner)
    points, breakdown = final_scores(state)[P1]
    assert breakdown["resources"] == 2
    assert points == sum(breakdown.values())


def test_trading_house_costs_less_next_to_an_opponent() -> None:
    swarmlings = FACTION_BY_TYPE[FactionType.SWARMLINGS]
    assert building_cost(swarmlings, BuildingType.TRADING_HOUSE, False).coins == 8
    assert building_cost(swarmlings, BuildingType.TRADING_HOUSE, True).coins == 4


def test_no_cult_bonus_after_the_final_round() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=1))
    state = replace(
        state,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
        players=tuple(replace(player, cults=(9, 9, 9, 9)) for player in state.players),
    )
    before = [player.resources.priests for player in state.players]
    transition = end_round(state, ())
    assert transition.state.phase == "game_over"
    assert [player.resources.priests for player in transition.state.players] == before
    assert all(event.kind != "cult_bonus" for event in transition.events)
    return


def test_play_match_and_replay() -> None:
    config = TerraMysticaConfig(num_players=2, rounds=1)
    sink = MemorySink()
    asyncio.run(
        play_match(
            GAME,
            config,
            9,
            random_agents(2, 9),
            match_id="terra-mystica-test",
            sink=sink,
            clock=FakeClock(),
        )
    )
    report = replay_match(sink.records)
    assert report.game_id == "terra_mystica"
    assert report.steps >= 1


def check_terra_mystica_state(state: TerraMysticaState) -> None:
    for player in state.players:
        resources = player.resources
        assert resources.coins >= 0
        assert resources.workers >= 0
        assert resources.priests >= 0
        assert resources.power <= 12
        assert 0 <= min(player.cults) <= max(player.cults) <= 10
        assert player.keys >= 0
    for seat in seats(len(state.players)):
        for building in BuildingType:
            assert state.board.count(seat, building) <= MAX_BUILDINGS[building]


def test_random_play_keeps_state_invariants() -> None:
    random_playthrough(
        GAME,
        TerraMysticaConfig(num_players=2, rounds=1),
        13,
        check_terra_mystica_state,
    )
