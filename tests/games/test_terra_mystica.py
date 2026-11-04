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
    Hex,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TerraMystica,
    TerraMysticaConfig,
    TerraMysticaState,
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
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    Income,
    Resources,
    ScoringAction,
    ScoringTile,
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
    replace_player,
    settle_town,
    shipping_points,
    spade_cost,
    spades_for,
    spend_power,
    town_ready,
)
from boardgames.games.terra_mystica.scoring import final_scores, split_rank_points
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


def test_shipping_extends_reach_across_a_river() -> None:
    for seed in range(20):
        state = play_setup(start(num_players=2, seed=seed))
        player = state.active_player
        for building in state.board.occupied(player):
            direct = state.board.reachable_from(building, 0)
            with_shipping = state.board.reachable_from(building, 1)
            extra = with_shipping - direct
            if extra:
                assert extra <= with_shipping
                assert not extra & direct
                return
    pytest.skip("no setup in the sampled seeds has a river crossing")


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
        isinstance(action, SendPriest | AdvanceCult) and action.cult is Cult.EARTH
        for action in listing(state)
    )
    owner = replace(state.players[player], keys=1)
    state = replace_player(state, player, owner)
    assert cult_limit(state.players[player]) == 10
    assert any(
        action.cult is Cult.EARTH
        for action in listing(state)
        if isinstance(action, SendPriest | AdvanceCult)
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
        isinstance(action, SendPriest | AdvanceCult) and action.cult is Cult.FIRE
        for action in listing(state)
    )


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


def test_notation_round_trips_for_every_legal_action() -> None:
    state = start(num_players=2, seed=1)
    while not GAME.is_terminal(state):
        for action in listing(state):
            text = GAME.format_action(action)
            assert GAME.parse_action(text) == action
        state = play(state, notations(state)[0])


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
        action for action in listing(state) if isinstance(action, UseCultSpade)
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
        action for action in listing(state) if isinstance(action, UseCultSpade)
    )
    tile = state.board.tile(spade.position)
    assert tile is not None
    player = state.players[decision.player]
    cost = spades_for(player.profile, tile.terrain)
    before = player.victory_points
    state = GAME.apply(state, decision.player, spade).state
    return state.players[decision.player].victory_points - before, cost


def test_cult_spade_points_follow_the_faction_bonus() -> None:
    gained, cost = cult_spade_points(FactionType.HALFLINGS)
    assert gained == cost
    gained, _ = cult_spade_points(FactionType.DARKLINGS)
    assert gained == 0


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
        cult_spades=(1, 2),
        active_player=state.order[0],
    )
    spade_text = GAME.render_text(GAME.observe(spade_state, None))
    assert "cult-bonus spade" in spade_text


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
    board, founded = settle_town(state.board, position, player)
    assert founded
    for hex_position in component:
        tile = board.tile(hex_position)
        assert tile is not None and tile.building is not None
        assert tile.building.in_town
    assert not settle_town(board, position, player)[1]
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
    assert not settle_town(weak, weak_positions[0], player)[1]


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
    after = GAME.apply(
        state, player, UpgradeBuilding(positions[3], BuildingType.TRADING_HOUSE)
    ).state.players[player]
    assert after.victory_points - before == 15
    assert after.keys == 1
    return


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
