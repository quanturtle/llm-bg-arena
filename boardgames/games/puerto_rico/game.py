"""Puerto Rico: the standard base game for 3, 4 or 5 players.

The game follows the role-selection cycle. Each round the players take turns
choosing an unchosen role; the role's action phase runs immediately, starting
with the player who chose it. Unchosen roles gain a doubloon at round end.
"""

from dataclasses import replace
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
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)
from boardgames.games.puerto_rico.constants import GOODS
from boardgames.games.puerto_rico.model import (
    Action,
    DiscardGoods,
    FinishPlacement,
    Pass,
    PuertoRicoConfig,
    PuertoRicoState,
    building_points,
    end_game_bonus,
    public_points,
    total_points,
)
from boardgames.games.puerto_rico.notation import format_action, parse_action
from boardgames.games.puerto_rico.roles.builder import (
    apply_builder,
    builder_actions,
    explain_builder,
)
from boardgames.games.puerto_rico.roles.captain import (
    apply_captain,
    apply_discard,
    captain_actions,
    discard_actions,
    explain_captain,
    explain_discard,
    kept_goods,
)
from boardgames.games.puerto_rico.roles.craftsman import (
    apply_craftsman,
    craftsman_actions,
    explain_craftsman,
)
from boardgames.games.puerto_rico.roles.mayor import (
    apply_mayor,
    explain_mayor,
    mayor_actions,
)
from boardgames.games.puerto_rico.roles.selection import (
    apply_selection,
    explain_selection,
    selection_actions,
)
from boardgames.games.puerto_rico.roles.settler import (
    apply_settler,
    explain_settler,
    settler_actions,
)
from boardgames.games.puerto_rico.roles.trader import (
    apply_trader,
    explain_trader,
    trader_actions,
)
from boardgames.games.puerto_rico.rounds import tiebreak_key
from boardgames.games.puerto_rico.setup import check_config, start_game
from boardgames.games.puerto_rico.view import (
    describe_action,
    observe,
    render_text,
)


@register_game
class PuertoRico(Game[PuertoRicoState, Action, PuertoRicoConfig]):
    """Puerto Rico with all base-game roles, buildings and end-game bonuses."""

    id: ClassVar[str] = "puerto_rico"
    rules_version: ClassVar[int] = 3

    # Config ---------------------------------------------------------------

    def parse_config(self, raw: JsonObject) -> PuertoRicoConfig:
        config = dataclass_from_json(PuertoRicoConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: PuertoRicoConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    # Setup ----------------------------------------------------------------

    def setup(self, config: PuertoRicoConfig, seed: int) -> Transition[PuertoRicoState]:
        return start_game(config, seed)

    # Decisions ------------------------------------------------------------

    def pending_decisions(self, state: PuertoRicoState) -> tuple[Decision, ...]:
        if state.phase == "game_over":
            return ()
        return (
            Decision(
                state.active_player,
                decision_kind(state.phase),
                decision_prompt(state),
            ),
        )

    def legal_actions(
        self, state: PuertoRicoState, decision: Decision
    ) -> ActionSpace[Action]:
        actions = legal_action_list(state, decision.player)
        default = default_action(state, actions)
        return FlatActionSpace(
            actions,
            format_action,
            explain=partial(explain_illegal, state, decision.player),
            default=default,
        )

    def apply(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        if isinstance(action, DiscardGoods):
            action = replace(
                action,
                protected=tuple(sorted(action.protected, key=GOODS.index)),
            )
        return checked_apply(
            self,
            state,
            player,
            action,
            no_decision=(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            ),
        )

    def apply_legal(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        """Apply an action already checked by `legal_actions`."""
        if state.phase == "role_selection":
            return apply_selection(state, player, action)
        if state.phase == "settler_action":
            return apply_settler(state, player, action)
        if state.phase == "mayor_action":
            return apply_mayor(state, player, action)
        if state.phase == "builder_action":
            return apply_builder(state, player, action)
        if state.phase == "craftsman_action":
            return apply_craftsman(state, player, action)
        if state.phase == "trader_action":
            return apply_trader(state, player, action)
        if state.phase == "captain_action":
            return apply_captain(state, player, action)
        if state.phase == "captain_discard":
            return apply_discard(state, player, action)
        raise IllegalActionError(f"no action is legal in phase {state.phase!r}")

    def is_terminal(self, state: PuertoRicoState) -> bool:
        return state.phase == "game_over"

    def scores(self, state: PuertoRicoState) -> Scores:
        points: dict[PlayerId, float] = {}
        breakdown: dict[PlayerId, dict[str, float]] = {}
        tiebreakers: dict[PlayerId, tuple[float, ...]] = {}
        for seat in range(state.config.num_players):
            player = state.players[seat]
            player_id = PlayerId(seat)
            base = total_points(player)
            points[player_id] = base
            breakdown[player_id] = {
                "vp_chips": player.vp_chips,
                "buildings": building_points(player),
                "bonus": end_game_bonus(player),
            }
            tiebreakers[player_id] = tuple(
                float(value) for value in tiebreak_key(state, player_id)
            )
        return Scores(points, breakdown, tiebreakers)

    def public_scores(self, state: PuertoRicoState) -> Scores:
        """VP chips stay hidden until the game ends and reveals them."""
        if self.is_terminal(state):
            return self.scores(state)
        return Scores(
            {
                PlayerId(seat): float(public_points(player))
                for seat, player in enumerate(state.players)
            },
            tiebreakers={
                PlayerId(seat): tuple(
                    float(value) for value in tiebreak_key(state, PlayerId(seat))
                )
                for seat in range(state.config.num_players)
            },
        )

    def observe(self, state: PuertoRicoState, viewer: PlayerId | None) -> Observation:
        return observe(state, viewer)

    def render_text(self, observation: Observation) -> str:
        return render_text(observation)

    def rules_text(self) -> str:
        rules = files("boardgames.games.puerto_rico") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Action) -> str:
        return format_action(action)

    def parse_action(self, text: str) -> Action:
        return parse_action(text)

    def describe_action(self, observation: Observation, action: Action) -> str:
        return describe_action(observation, action)

    def action_json(self, action: Action) -> dict[str, JsonValue]:
        return tagged_json_object(action)


# Helpers ------------------------------------------------------------------


def legal_action_list(state: PuertoRicoState, player: PlayerId) -> list[Action]:
    """Every action the deciding player may choose right now."""
    if state.phase == "role_selection":
        return selection_actions(state)
    owner = state.players[player]
    if state.phase == "settler_action":
        return settler_actions(state, player, owner)
    if state.phase == "mayor_action":
        return mayor_actions(owner)
    if state.phase == "builder_action":
        return builder_actions(state, player)
    if state.phase == "craftsman_action":
        return craftsman_actions(state, owner)
    if state.phase == "trader_action":
        return trader_actions(state, owner)
    if state.phase == "captain_action":
        return captain_actions(state, player, owner)
    if state.phase == "captain_discard":
        return discard_actions(owner)
    return []


def default_action(state: PuertoRicoState, actions: list[Action]) -> Action | None:
    """A safe fallback for phases where passing is allowed."""
    if state.phase in (
        "settler_action",
        "builder_action",
        "trader_action",
        "craftsman_action",
    ):
        return Pass()
    if state.phase == "mayor_action":
        return FinishPlacement() if FinishPlacement() in actions else None
    if state.phase == "captain_discard":
        discards = [action for action in actions if isinstance(action, DiscardGoods)]
        return max(
            discards,
            key=lambda action: kept_goods(state.players[state.active_player], action),
        )
    return None


def decision_kind(phase: str) -> str:
    return {
        "role_selection": "role",
        "settler_action": "settler",
        "mayor_action": "mayor",
        "builder_action": "builder",
        "craftsman_action": "craftsman",
        "trader_action": "trader",
        "captain_action": "captain",
        "captain_discard": "captain_discard",
    }.get(phase, phase)


def decision_prompt(state: PuertoRicoState) -> str:
    if state.phase == "role_selection":
        return "Choose an unchosen role."
    if state.phase == "settler_action":
        return "Take a plantation or quarry, or pass."
    if state.phase == "mayor_action":
        return "Place or move a colonist, or finish placement."
    if state.phase == "builder_action":
        return "Build a building or pass."
    if state.phase == "craftsman_action":
        return "Take the Craftsman privilege or pass."
    if state.phase == "trader_action":
        return "Sell a good or pass."
    if state.phase == "captain_action":
        return "Load goods on a ship or Wharf, or pass if you cannot."
    if state.phase == "captain_discard":
        return "Choose which goods to keep after shipping."
    return "Choose an action."


def explain_illegal(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why `action` is not legal for `player` now."""
    phase = state.phase
    if phase == "role_selection":
        return explain_selection(state, action)
    if phase == "settler_action":
        return explain_settler(state, player, action)
    if phase == "mayor_action":
        return explain_mayor(state, player, action)
    if phase == "builder_action":
        return explain_builder(state, player, action)
    if phase == "craftsman_action":
        return explain_craftsman(state, player, action)
    if phase == "trader_action":
        return explain_trader(state, player, action)
    if phase == "captain_action":
        return explain_captain(state, player, action)
    if phase == "captain_discard":
        return explain_discard(state, player, action)
    return "That action is not legal now."
