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
    Event,
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
from boardgames.games.puerto_rico.constants import (
    GOODS,
    Role,
)
from boardgames.games.puerto_rico.model import (
    Action,
    DiscardGoods,
    FinishPlacement,
    Pass,
    Phase,
    PuertoRicoConfig,
    PuertoRicoState,
    SelectRole,
    building_points,
    end_game_bonus,
    public_points,
    replace_player,
    replace_role,
    role_state,
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
    run_production,
)
from boardgames.games.puerto_rico.roles.mayor import (
    apply_mayor,
    distribute_colonists,
    explain_mayor,
    mayor_actions,
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
from boardgames.games.puerto_rico.rounds import advance_role_picker, tiebreak_key
from boardgames.games.puerto_rico.setup import check_config, start_game
from boardgames.games.puerto_rico.view import (
    describe_action,
    observe,
    render_text,
)

ROLE_PHASE: dict[Role, Phase] = {
    "settler": "settler_action",
    "mayor": "mayor_action",
    "builder": "builder_action",
    "craftsman": "craftsman_action",
    "trader": "trader_action",
    "captain": "captain_action",
}


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
            if not isinstance(action, SelectRole):
                raise IllegalActionError("choose a role now")
            return self.take_role(state, player, action.role)
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

    # Role selection -------------------------------------------------------

    def take_role(
        self, state: PuertoRicoState, player: PlayerId, role: Role
    ) -> Transition[PuertoRicoState]:
        role_entry = role_state(state, role)
        if role_entry.taken_by is not None:
            raise IllegalActionError(f"{role} has already been chosen this round")
        if player != state.active_player:
            raise IllegalActionError(f"it is not {seat_label(player)}'s turn")
        owner = state.players[player]
        owner = replace(owner, doubloons=owner.doubloons + role_entry.doubloons)
        state = replace_player(state, player, owner)
        state = replace_role(
            state, role, replace(role_entry, doubloons=0, taken_by=player)
        )
        events = [
            Event(
                "role_taken",
                f"{seat_label(player)} chose {role} "
                f"(+{role_entry.doubloons} doubloons).",
                {
                    "player": player,
                    "role": role,
                    "doubloons": role_entry.doubloons,
                },
            )
        ]
        if role in ("prospector", "prospector_2"):
            owner = replace(
                state.players[player], doubloons=state.players[player].doubloons + 1
            )
            state = replace_player(state, player, owner)
            events.append(
                Event(
                    "prospector_bonus",
                    f"{seat_label(player)} took a prospector: +1 doubloon.",
                    {"player": player, "doubloons": 1},
                )
            )
            state = advance_role_picker(state)
            return Transition(state, tuple(events))
        state, phase_events = self.start_role_phase(state, role, player)
        events.extend(phase_events)
        return Transition(state, tuple(events))

    def start_role_phase(
        self, state: PuertoRicoState, role: Role, player: PlayerId
    ) -> tuple[PuertoRicoState, tuple[Event, ...]]:
        phase = ROLE_PHASE[role]
        state = replace(
            state,
            active_role=role,
            phase=phase,
            active_player=player,
            players_acted=frozenset(),
            captain_passes=0,
        )
        events: list[Event] = []
        if role == "settler":
            state = replace(
                state,
                players=tuple(
                    replace(item, hacienda_used=False) for item in state.players
                ),
            )
        elif role == "mayor":
            has_extra = state.colonist_supply > 0
            state = distribute_colonists(state, player)
            events.append(
                Event(
                    "colonists_distributed",
                    "Colonists from the ship are distributed; "
                    + (
                        f"{seat_label(player)} takes the extra colonist."
                        if has_extra
                        else "the supply is empty, so there is no extra colonist."
                    ),
                    {"player": player},
                )
            )
        elif role == "craftsman":
            state, produced_events = run_production(state, player)
            events.extend(produced_events)
        elif role == "captain":
            state = replace(
                state,
                players=tuple(
                    replace(
                        item,
                        captain_first_load_done=False,
                        wharf_used=False,
                    )
                    for item in state.players
                ),
            )
        return state, tuple(events)


# Helpers ------------------------------------------------------------------


def legal_action_list(state: PuertoRicoState, player: PlayerId) -> list[Action]:
    """Every action the deciding player may choose right now."""
    if state.phase == "role_selection":
        return [SelectRole(role.role) for role in state.roles if role.taken_by is None]
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
        if isinstance(action, SelectRole):
            entry = next(
                (item for item in state.roles if item.role == action.role), None
            )
            if entry is None:
                return f"There is no {action.role} role in this game."
            if entry.taken_by is not None:
                return f"{action.role} was already chosen this round."
        return "Choose a role that nobody has taken this round."
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
