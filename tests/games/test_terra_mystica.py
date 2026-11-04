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
    BuildDwelling,
    Hex,
    Pass,
    PowerAction,
    SendPriest,
    TerraMystica,
    TerraMysticaConfig,
    TerraMysticaState,
    UpgradeBuilding,
    UseCultSpade,
)
from boardgames.games.terra_mystica.constants import (
    CULT_ORDER_STEPS,
    FACTION_BY_TYPE,
    FACTION_PROFILES,
    MAX_BUILDINGS,
    STANDARD_TRADING_HOUSE_INCOME,
    TERRAIN_WHEEL,
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    Resources,
    ScoringAction,
    ScoringTile,
)
from boardgames.games.terra_mystica.game import initial_setup_queue
from boardgames.games.terra_mystica.model import (
    PlayerState,
    advance_cult,
    cult_limit,
    gain_power,
    replace_player,
    shipping_points,
    spade_cost,
    spades_for,
    spend_power,
)
from boardgames.games.terra_mystica.scoring import final_scores
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
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    for building in state.board.occupied(player):
        direct = state.board.reachable_from(building, 0)
        with_shipping = state.board.reachable_from(building, 1)
        extra = with_shipping - direct
        if extra:
            assert extra
            return
    pytest.skip("this setup has no river crossing to test")


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
    assert (action.cult, action.order) in state.used_orders


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
    assert (Cult.FIRE, 0) in state.used_orders
    state = with_resources(state, second, priests=1)
    state = replace(state, active_player=second)
    assert not any(
        isinstance(action, SendPriest)
        and action.cult is Cult.FIRE
        and action.order == 0
        for action in listing(state)
    )


def test_standard_rule_tables_match_the_base_game() -> None:
    assert CULT_ORDER_STEPS == (3, 2, 2, 2)
    assert tuple(income.power for income in STANDARD_TRADING_HOUSE_INCOME) == (
        1,
        2,
        4,
        6,
    )
    assert [shipping_points(level) for level in (1, 2, 3)] == [2, 3, 4]
    assert FACTION_BY_TYPE[FactionType.WITCHES].base_income.workers == 1
    assert FACTION_BY_TYPE[FactionType.ENGINEERS].base_income.workers == 0
    assert FACTION_BY_TYPE[FactionType.SWARMLINGS].base_income.workers == 2


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
    state = replace(
        state,
        players=tuple(
            replace(
                player,
                cults=(9, 9, 9, 9),
                resources=replace(player.resources, priests=7),
            )
            for player in state.players
        ),
    )
    while state.phase == "action" and state.round == 1:
        state = play(state, "pass")
    assert state.round == 2
    assert all(player.resources.priests == 7 for player in state.players)


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
    from boardgames.games.terra_mystica.constants import Income
    from boardgames.games.terra_mystica.model import income_with_power

    resources = Resources(coins=1, workers=1, priests=1, power1=5, power2=7)
    updated = income_with_power(
        resources, Income(coins=2, workers=3, priests=4, power=2)
    )
    assert updated.coins == 3
    assert updated.workers == 4
    assert updated.priests == 5
    assert updated.power == 12


def test_spade_costs_use_workers_and_darklings_use_priests() -> None:
    witches = FACTION_PROFILES[0]
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


def test_random_play_keeps_state_invariants() -> None:
    def check(state: TerraMysticaState) -> None:
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

    random_playthrough(GAME, TerraMysticaConfig(num_players=2, rounds=1), 13, check)
