"""Terra Mystica faction special actions."""

from dataclasses import replace

from boardgames.core import Event, IllegalActionError, PlayerId, Transition, seat_label
from boardgames.games.terra_mystica.bonus import effective_shipping
from boardgames.games.terra_mystica.building import build_dwelling, upgrade_building
from boardgames.games.terra_mystica.constants import (
    SCORING_VALUES,
    BuildingType,
    Cult,
    FactionType,
    ScoringAction,
)
from boardgames.games.terra_mystica.cults import cult_top_occupied
from boardgames.games.terra_mystica.model import (
    Action,
    BonusSpade,
    ChaosDoubleTurn,
    GiantsSpades,
    NomadsSandstorm,
    SpecialCult,
    SwarmlingsUpgrade,
    TerraMysticaState,
    WitchesRide,
    advance_cult,
    can_place_building,
    replace_at,
    replace_player,
)
from boardgames.games.terra_mystica.rounds import advance_turn, round_scoring
from boardgames.games.terra_mystica.spade_gain import gain_spade_power

SPECIAL_AUREN = "auren"
SPECIAL_WATER_FAVOR = "water_favor"
SPECIAL_BONUS_CULT = "bonus_cult"
SPECIAL_WITCHES = "witches"
SPECIAL_SWARMLINGS = "swarmlings"
SPECIAL_CHAOS = "chaos"
SPECIAL_GIANTS = "giants"
SPECIAL_NOMADS = "nomads"


def has_stronghold(state: TerraMysticaState, player: PlayerId) -> bool:
    return state.board.count(player, BuildingType.STRONGHOLD) > 0


def _unused(state: TerraMysticaState, kind: str) -> bool:
    return kind not in state.used_special_actions


def _water_key(player: PlayerId) -> str:
    """The Water favor action is per holder, not once for the whole table."""
    return f"{SPECIAL_WATER_FAVOR}:{player}"


def special_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    """Every faction special action the player can take now."""
    owner = state.players[player]
    profile = owner.profile
    actions: list[Action] = []
    if (
        profile.type is FactionType.AUREN
        and has_stronghold(state, player)
        and _unused(state, SPECIAL_AUREN)
    ):
        actions.extend(SpecialCult("auren", cult) for cult in Cult)
    if 5 in owner.favors and _unused(state, _water_key(player)):
        actions.extend(SpecialCult("water_favor", cult) for cult in Cult)
    if owner.bonus_card == 5 and _unused(state, SPECIAL_BONUS_CULT):
        actions.extend(SpecialCult("bonus", cult) for cult in Cult)
    if owner.bonus_card == 4 and _unused(state, "bonus_spade"):
        actions.append(BonusSpade())
    if has_stronghold(state, player):
        if profile.type is FactionType.WITCHES and _unused(state, SPECIAL_WITCHES):
            actions.extend(
                WitchesRide(tile.position)
                for tile in state.board.tiles
                if tile.is_land
                and tile.terrain is owner.home_terrain
                and tile.building is None
                and can_place_building(state.board, player, BuildingType.DWELLING)
            )
        if profile.type is FactionType.SWARMLINGS and _unused(
            state, SPECIAL_SWARMLINGS
        ):
            actions.extend(
                SwarmlingsUpgrade(position)
                for position, building in state.board.buildings(player)
                if building.type is BuildingType.DWELLING
                and can_place_building(state.board, player, BuildingType.TRADING_HOUSE)
            )
        if profile.type is FactionType.CHAOS_MAGICIANS and _unused(
            state, SPECIAL_CHAOS
        ):
            actions.append(ChaosDoubleTurn())
        if profile.type is FactionType.GIANTS and _unused(state, SPECIAL_GIANTS):
            reachable = state.board.reachable_land(
                player, effective_shipping(state, player), 0, state.bridges
            )
            actions.extend(
                GiantsSpades(tile.position)
                for tile in state.board.tiles
                if tile.is_land
                and tile.building is None
                and tile.terrain is not owner.home_terrain
                and tile.position in reachable
            )
        if profile.type is FactionType.NOMADS and _unused(state, SPECIAL_NOMADS):
            adjacent = {
                neighbour
                for position in state.board.occupied(player)
                for neighbour in position.neighbours()
            }
            actions.extend(
                NomadsSandstorm(tile.position)
                for tile in state.board.tiles
                if tile.is_land
                and tile.building is None
                and tile.terrain is not owner.home_terrain
                and tile.position in adjacent
            )
    return actions


def take_special_action(
    state: TerraMysticaState, player: PlayerId, action: Action
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    profile = owner.profile
    if not has_stronghold(state, player) and not isinstance(
        action, (SpecialCult, BonusSpade)
    ):
        raise IllegalActionError("your stronghold is needed for that action")
    if isinstance(action, SpecialCult):
        kind = (
            SPECIAL_AUREN
            if action.source == "auren"
            else _water_key(player)
            if action.source == "water_favor"
            else SPECIAL_BONUS_CULT
        )
        if profile.type is not FactionType.AUREN and action.source == "auren":
            raise IllegalActionError("only the Auren have that action")
        if action.source == "water_favor" and 5 not in owner.favors:
            raise IllegalActionError("you do not have that favor tile")
        if action.source == "bonus" and owner.bonus_card != 5:
            raise IllegalActionError("you do not have that bonus card")
    elif isinstance(action, WitchesRide):
        kind = SPECIAL_WITCHES
        if profile.type is not FactionType.WITCHES:
            raise IllegalActionError("only the Witches may ride")
        tile = state.board.tile(action.position)
        if tile is None or not tile.is_land or tile.building is not None:
            raise IllegalActionError("choose an empty forest space")
        if tile.terrain is not profile.home_terrain:
            raise IllegalActionError("Witches may only ride to a forest space")
        state = replace(
            state,
            used_special_actions=state.used_special_actions | {kind},
        )
        return build_dwelling(
            state, player, action.position, free=True, ignore_reach=True
        )
    elif isinstance(action, SwarmlingsUpgrade):
        kind = SPECIAL_SWARMLINGS
        if profile.type is not FactionType.SWARMLINGS:
            raise IllegalActionError("only the Swarmlings may take that action")
        state = replace(
            state,
            used_special_actions=state.used_special_actions | {kind},
        )
        return upgrade_building(
            state, player, action.position, BuildingType.TRADING_HOUSE, free=True
        )
    elif isinstance(action, BonusSpade):
        kind = "bonus_spade"
        if owner.bonus_card != 4:
            raise IllegalActionError("you do not have that bonus card")
        if kind in state.used_special_actions:
            raise IllegalActionError("that special action was already used this round")
        if profile.spade_vp_bonus:
            owner = replace(
                owner,
                victory_points=owner.victory_points + profile.spade_vp_bonus,
            )
            state = replace_player(state, player, owner)
        state = gain_spade_power(state, player, 1)
        state = replace(
            state,
            used_special_actions=state.used_special_actions | {kind},
            phase="cult_spades",
            cult_spades=replace_at(state.cult_spades, player, 1),
            spade_return="action",
            spade_actor=player,
            power_spade_tiles=(),
            spade_second=None,
            spade_transformed=(),
            spade_intermediate=False,
            spade_reach_used=False,
            spade_topup=True,
            spade_require_all=False,
            active_player=player,
        )
        event = Event(
            "special_action",
            f"{seat_label(player)} took a free spade from a bonus card.",
            {"player": player, "kind": kind, "spades": 1},
        )
        return Transition(state, (event,))
    elif isinstance(action, ChaosDoubleTurn):
        kind = SPECIAL_CHAOS
        if profile.type is not FactionType.CHAOS_MAGICIANS:
            raise IllegalActionError("only the Chaos Magicians may take a double turn")
        state = replace(
            state,
            used_special_actions=state.used_special_actions | {kind},
            extra_actions=2,
        )
        event = Event(
            "special_action",
            f"{seat_label(player)} took a double turn.",
            {"player": player, "kind": kind},
        )
        return Transition(state, (event,))
    elif isinstance(action, (GiantsSpades, NomadsSandstorm)):
        return _transform_for_free(state, player, action)
    else:
        raise IllegalActionError("unknown special action")

    if kind in state.used_special_actions:
        raise IllegalActionError("that special action was already used this round")
    state = replace(state, used_special_actions=state.used_special_actions | {kind})
    owner, power = advance_cult(
        owner,
        action.cult,
        2 if action.source == "auren" else 1,
        top_occupied=cult_top_occupied(state, player, action.cult),
    )
    state = replace_player(state, player, owner)
    event = Event(
        "special_action",
        f"{seat_label(player)} advanced {action.cult.value} by "
        f"{2 if action.source == 'auren' else 1} from a special action "
        f"and gained {power} power.",
        {
            "player": player,
            "kind": kind,
            "cult": action.cult.value,
            "steps": 2 if action.source == "auren" else 1,
            "power": power,
        },
    )
    return advance_turn(state, player, (event,))


def _transform_for_free(
    state: TerraMysticaState,
    player: PlayerId,
    action: GiantsSpades | NomadsSandstorm,
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    profile = owner.profile
    if isinstance(action, GiantsSpades):
        kind = SPECIAL_GIANTS
        if profile.type is not FactionType.GIANTS:
            raise IllegalActionError("only the Giants may take that action")
        reachable = state.board.reachable_land(
            player, effective_shipping(state, player), 0, state.bridges
        )
        if action.position not in reachable:
            raise IllegalActionError("that tile is not reachable")
    else:
        kind = SPECIAL_NOMADS
        if profile.type is not FactionType.NOMADS:
            raise IllegalActionError("only the Nomads may call a sandstorm")
        adjacent = {
            neighbour
            for position in state.board.occupied(player)
            for neighbour in position.neighbours()
        }
        if action.position not in adjacent:
            raise IllegalActionError(
                "the sandstorm must be next to one of your structures"
            )
    if kind in state.used_special_actions:
        raise IllegalActionError("that special action was already used this round")
    tile = state.board.tile(action.position)
    if tile is None or not tile.is_land or tile.building is not None:
        raise IllegalActionError("choose an empty land tile")
    if tile.terrain is profile.home_terrain:
        raise IllegalActionError("that tile is already your home terrain")
    if isinstance(action, GiantsSpades) and round_scoring(state) is ScoringAction.SPADE:
        owner = replace(
            owner,
            victory_points=owner.victory_points
            + 2 * SCORING_VALUES[ScoringAction.SPADE],
        )
        state = replace_player(state, player, owner)
    state = replace(
        state,
        board=state.board.replace_tile(
            action.position, replace(tile, terrain=profile.home_terrain)
        ),
        used_special_actions=state.used_special_actions | {kind},
        phase="cult_spades",
        cult_spades=replace_at(state.cult_spades, player, 0),
        spade_return="action",
        spade_actor=player,
        power_spade_tiles=(action.position,),
        spade_second=None,
        spade_transformed=(),
        spade_intermediate=False,
        spade_reach_used=False,
        spade_topup=False,
        spade_require_all=False,
        active_player=player,
    )
    event = Event(
        "special_action",
        f"{seat_label(player)} transformed {action.position.notation()} into "
        f"{profile.home_terrain.value} with a special action.",
        {
            "player": player,
            "kind": kind,
            "position": action.position.notation(),
        },
    )
    return Transition(state, (event,))


def explain_special(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    legal = special_actions(state, player)
    if isinstance(
        action, (WitchesRide, SwarmlingsUpgrade, GiantsSpades, NomadsSandstorm)
    ) and action.position not in {
        candidate.position for candidate in legal if isinstance(candidate, type(action))
    }:
        return "That special action is not legal now."
    if isinstance(action, (SpecialCult, ChaosDoubleTurn)) and action not in legal:
        return "That special action was already used this round."
    return "That special action cannot be taken now."
