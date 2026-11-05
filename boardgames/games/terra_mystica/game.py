"""Terra Mystica: the standard base game for two to five players."""

from functools import partial
from importlib.resources import files
from typing import ClassVar

from boardgames.core import (
    ActionSpace,
    Decision,
    FlatActionSpace,
    Game,
    IllegalActionError,
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    Scores,
    Transition,
    checked_apply,
    register_game,
    seat_label,
    seats,
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)
from boardgames.games.terra_mystica.building import (
    advance_digging,
    advance_shipping,
    build_dwelling,
    building_actions,
    explain_build,
    explain_digging,
    explain_shipping,
    explain_transform,
    explain_upgrade,
    transform_terrain,
    upgrade_building,
)
from boardgames.games.terra_mystica.cults import (
    advance_cult_with_priest,
    explain_advance_cult,
    explain_send_priest,
    priest_actions,
    send_priest,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BuildDwelling,
    ChooseStrongholdPriests,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TakeTownTile,
    TerraMysticaConfig,
    TerraMysticaState,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.notation import format_action, parse_action
from boardgames.games.terra_mystica.power import (
    alchemist_trades,
    explain_power_action,
    explain_trade_coins_for_vp,
    explain_trade_vp_for_coin,
    power_actions,
    take_power_action,
    trade_coins_for_vp,
    trade_vp_for_coin,
)
from boardgames.games.terra_mystica.rounds import pass_turn
from boardgames.games.terra_mystica.scoring import final_scores
from boardgames.games.terra_mystica.setup import (
    check_config,
    explain_setup,
    place_starting_dwelling,
    setup_actions,
    start_game,
)
from boardgames.games.terra_mystica.spades import (
    apply_spade_phase,
    cult_spade_actions,
    explain_spade,
)
from boardgames.games.terra_mystica.strongholds import (
    choose_stronghold_priests,
    convert_actions,
    explain_convert,
)
from boardgames.games.terra_mystica.towns import (
    explain_town_choice,
    take_town_tile,
    town_tile_actions,
)
from boardgames.games.terra_mystica.view import (
    describe_action,
    observe,
    render_text,
)


@register_game
class TerraMystica(Game[TerraMysticaState, Action, TerraMysticaConfig]):
    """The base game: six rounds, fourteen factions and the standard map."""

    id: ClassVar[str] = "terra_mystica"
    rules_version: ClassVar[int] = 7

    # Config ---------------------------------------------------------------

    def parse_config(self, raw: JsonObject) -> TerraMysticaConfig:
        config = dataclass_from_json(TerraMysticaConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: TerraMysticaConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    # Setup ----------------------------------------------------------------

    def setup(
        self, config: TerraMysticaConfig, seed: int
    ) -> Transition[TerraMysticaState]:
        return start_game(config, seed)

    # Decisions ------------------------------------------------------------

    def pending_decisions(self, state: TerraMysticaState) -> tuple[Decision, ...]:
        if state.phase == "game_over":
            return ()
        if state.phase == "setup":
            return (
                Decision(
                    state.active_player,
                    "setup_dwelling",
                    "Place one of your starting dwellings on a free home-terrain tile.",
                ),
            )
        if state.phase == "cult_spades":
            kind = "spade" if state.spade_return == "action" else "cult-bonus spade"
            return (
                Decision(
                    state.active_player,
                    "cult_spade",
                    f"Spend a {kind} on a reachable tile, or skip.",
                ),
            )
        if state.phase == "stronghold_convert":
            return (
                Decision(
                    state.active_player,
                    "stronghold_convert",
                    "Trade up to three workers for one priest each.",
                ),
            )
        if state.phase == "town_choice":
            return (
                Decision(
                    state.active_player,
                    "town_choice",
                    "Choose one of the remaining town tiles.",
                ),
            )
        return (
            Decision(
                state.active_player,
                "action",
                "Take one action, or pass when you are done.",
            ),
        )

    def legal_actions(
        self, state: TerraMysticaState, decision: Decision
    ) -> ActionSpace[Action]:
        actions = legal_action_list(state, decision.player)
        default = (
            Pass()
            if state.phase == "action"
            else SkipCultSpade()
            if state.phase == "cult_spades"
            else None
        )
        return FlatActionSpace(
            actions,
            format_action,
            explain=partial(explain_illegal, state, decision.player),
            default=default,
        )

    def apply(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        return checked_apply(
            self,
            state,
            player,
            action,
            no_decision=(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            ),
        )

    # Rules ----------------------------------------------------------------

    def apply_legal(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        if state.phase == "setup":
            if not isinstance(action, BuildDwelling):
                raise IllegalActionError("place a starting dwelling now")
            return place_starting_dwelling(state, player, action.position)
        if state.phase == "cult_spades":
            return apply_spade_phase(state, player, action)
        if state.phase == "stronghold_convert":
            if not isinstance(action, ChooseStrongholdPriests):
                raise IllegalActionError("choose how many workers to trade")
            return choose_stronghold_priests(state, player, action.workers)
        if state.phase == "town_choice":
            if not isinstance(action, TakeTownTile):
                raise IllegalActionError("choose a town tile now")
            return take_town_tile(state, player, action.index)
        if state.phase != "action":
            raise IllegalActionError("the game is over")
        if player != state.active_player:
            raise IllegalActionError(f"it is {seat_label(state.active_player)}'s turn")
        return self.apply_action(state, player, action)

    def is_terminal(self, state: TerraMysticaState) -> bool:
        return state.phase == "game_over"

    def scores(self, state: TerraMysticaState) -> Scores:
        if self.is_terminal(state):
            final = final_scores(state)
            return Scores(
                {
                    player: float(final[player][0])
                    for player in seats(len(state.players))
                },
                {player: final[player][1] for player in seats(len(state.players))},
            )
        return Scores(
            {
                player: float(state.players[player].victory_points)
                for player in seats(len(state.players))
            }
        )

    def public_scores(self, state: TerraMysticaState) -> Scores:
        """Terra Mystica has no hidden victory points."""
        return self.scores(state)

    def observe(self, state: TerraMysticaState, viewer: PlayerId | None) -> Observation:
        return observe(state, viewer)

    def render_text(self, observation: Observation) -> str:
        return render_text(observation)

    def rules_text(self) -> str:
        rules = files("boardgames.games.terra_mystica") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Action) -> str:
        return format_action(action)

    def parse_action(self, text: str) -> Action:
        return parse_action(text)

    def describe_action(self, observation: Observation, action: Action) -> str:
        return describe_action(observation, action)

    def action_json(self, action: Action) -> dict[str, JsonValue]:
        return tagged_json_object(action)

    # Round plumbing -------------------------------------------------------

    def apply_action(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        if isinstance(action, BuildDwelling):
            return build_dwelling(state, player, action.position, action.river)
        if isinstance(action, TransformTerrain):
            return transform_terrain(state, player, action.position, action.to)
        if isinstance(action, UpgradeBuilding):
            return upgrade_building(
                state, player, action.position, action.to, action.river
            )
        if isinstance(action, AdvanceShipping):
            return advance_shipping(state, player)
        if isinstance(action, AdvanceDigging):
            return advance_digging(state, player)
        if isinstance(action, SendPriest):
            return send_priest(state, player, action.cult, action.order)
        if isinstance(action, AdvanceCult):
            return advance_cult_with_priest(state, player, action.cult)
        if isinstance(action, PowerAction):
            return take_power_action(state, player, action.kind)
        if isinstance(action, TradeVpForCoin):
            return trade_vp_for_coin(state, player)
        if isinstance(action, TradeCoinsForVp):
            return trade_coins_for_vp(state, player)
        if isinstance(action, Pass):
            return pass_turn(state, player)
        raise IllegalActionError("unknown action")


def legal_action_list(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    if state.phase == "setup":
        return setup_actions(state, player)
    if state.phase == "cult_spades":
        return cult_spade_actions(state, player)
    if state.phase == "stronghold_convert":
        return convert_actions(state, player)
    if state.phase == "town_choice":
        return town_tile_actions(state)
    if state.phase != "action":
        return []
    if player != state.active_player:
        return []
    return action_phase_actions(state, player)


def action_phase_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    actions = building_actions(state, player)
    actions.extend(priest_actions(state, player))
    actions.extend(power_actions(state, player))
    actions.extend(alchemist_trades(state, player))
    actions.append(Pass())
    return actions


def explain_illegal(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    if state.phase == "setup":
        return explain_setup(state, player, action)
    if state.phase == "cult_spades":
        return explain_spade(state, player, action)
    if state.phase == "stronghold_convert":
        return explain_convert(state, player, action)
    if state.phase == "town_choice":
        return explain_town_choice(state, action)
    if state.phase != "action":
        return "The game is over."
    if player != state.active_player:
        return f"It is {seat_label(state.active_player)}'s turn."
    if isinstance(action, BuildDwelling):
        return explain_build(state, player, action)
    if isinstance(action, TransformTerrain):
        return explain_transform(state, player, action)
    if isinstance(action, UpgradeBuilding):
        return explain_upgrade(state, player, action)
    if isinstance(action, AdvanceShipping):
        return explain_shipping(state, player)
    if isinstance(action, AdvanceDigging):
        return explain_digging(state, player)
    if isinstance(action, SendPriest):
        return explain_send_priest(state, player, action)
    if isinstance(action, AdvanceCult):
        return explain_advance_cult(state, player, action)
    if isinstance(action, PowerAction):
        return explain_power_action(state, player, action)
    if isinstance(action, TradeVpForCoin):
        return explain_trade_vp_for_coin(state, player)
    if isinstance(action, TradeCoinsForVp):
        return explain_trade_coins_for_vp(state, player)
    if isinstance(action, Pass):
        return "Passing is always legal."
    return "That action is not legal now."
