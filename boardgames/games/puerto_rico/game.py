"""Puerto Rico: the standard base game for 3, 4 or 5 players.

The game follows the role-selection cycle. Each round the players take turns
choosing an unchosen role; the role's action phase runs immediately, starting
with the player who chose it. Unchosen roles gain a doubloon at round end.

`PuertoRico` is the facade the framework calls. The rules live in `setup`,
`rounds`, `decisions` and one module per role in `roles/`.
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
from boardgames.games.puerto_rico.decisions import (
    decision_kind,
    decision_prompt,
    default_action,
    explain_illegal,
    legal_action_list,
)
from boardgames.games.puerto_rico.model import (
    Action,
    DiscardGoods,
    PuertoRicoConfig,
    PuertoRicoState,
    building_points,
    end_game_bonus,
    public_points,
    total_points,
)
from boardgames.games.puerto_rico.notation import format_action, parse_action
from boardgames.games.puerto_rico.roles.builder import apply_builder
from boardgames.games.puerto_rico.roles.captain import apply_captain, apply_discard
from boardgames.games.puerto_rico.roles.craftsman import apply_craftsman
from boardgames.games.puerto_rico.roles.mayor import apply_mayor
from boardgames.games.puerto_rico.roles.selection import apply_selection
from boardgames.games.puerto_rico.roles.settler import apply_settler
from boardgames.games.puerto_rico.roles.trader import apply_trader
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
