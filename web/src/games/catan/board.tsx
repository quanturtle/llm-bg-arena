import {
  ArrowRight,
  Award,
  CircleCheck,
  Coins,
  Construction,
  Dice1,
  Dice2,
  Dice3,
  Dice4,
  Dice5,
  Dice6,
  Dices,
  Flag,
  Gift,
  HandGrab,
  Handshake,
  House,
  Landmark,
  Layers,
  Map as MapIcon,
  MessageSquare,
  Play,
  Route,
  Shield,
  Sparkles,
  Square,
  Swords,
  ThumbsDown,
  Trash2,
  TriangleAlert,
  Trophy,
  VenetianMask,
  Wheat,
  Building2,
} from "lucide-react";

import { StatusBar } from "@/components/board-parts";
import { SeatChip } from "@/components/seat";
import { CatanBoardSvg } from "@/games/catan/board-svg";
import { layoutSchema, observationSchema, type CatanObservation } from "@/games/catan/observation";
import { CatanPlayers } from "@/games/catan/players";
import { defineGame, type BoardContext } from "@/games/define";
import type { MatchSummary } from "@/lib/api";

const DICE = [Dice1, Dice2, Dice3, Dice4, Dice5, Dice6];

function CatanStatus({ observation, match, pending }: { observation: CatanObservation; match: MatchSummary; pending: number[] }) {
  if (observation.game_over) {
    const winner = observation.winner === null ? null : match.seats[observation.winner];
    return (
      <StatusBar tone="done">
        <Trophy className="size-4 shrink-0" />
        {winner ? (
          <>
            Game over: <SeatChip seat={winner} link={false} className="min-w-0" /> won.
          </>
        ) : (
          "Game over."
        )}
      </StatusBar>
    );
  }
  const dice = observation.dice;
  const acting = pending.map((player) => match.seats[player]).filter((seat) => seat !== undefined);
  return (
    <StatusBar
      aside={
        dice ? (
          <span className="flex items-center gap-0.5 text-muted-foreground" title={`Rolled ${dice.join(" + ")}`}>
            {dice.map((value, index) => {
              const Face = DICE[value - 1] ?? Dices;
              return <Face key={index} className="size-5" />;
            })}
            <span className="ml-1 w-[3ch] font-semibold text-foreground tabular-nums">= {dice.reduce((sum, value) => sum + value, 0)}</span>
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">no roll yet</span>
        )
      }
    >
      <span className="font-semibold tabular-nums">Turn {observation.turn}</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">{observation.phase.replace(/_/g, " ")}</span>
      {acting.length ? (
        <>
          <span className="text-muted-foreground">·</span>
          {acting.map((seat, index) => (
            <span key={index} className="flex items-center gap-1">
              <SeatChip seat={seat} link={false} className="min-w-0" />
              <span className="shrink-0 text-muted-foreground">to act</span>
            </span>
          ))}
        </>
      ) : null}
    </StatusBar>
  );
}

// Wide boards put the players beside the map; narrow ones stack them below it. On desktop the
// map shrinks to the panel's height, so the whole board shows without scrolling.
function CatanBoard({ observation, context }: { observation: CatanObservation; context: BoardContext }) {
  const layout = layoutSchema.safeParse(context.layout);
  if (!layout.success) return <p className="text-sm text-destructive">The Catan layout did not load: {layout.error.message}</p>;
  return (
    <div className="@container flex flex-col gap-3 xl:h-full">
      <CatanStatus observation={observation} match={context.match} pending={context.frame.pending} />
      <div className="grid gap-4 @3xl:grid-cols-[minmax(0,1fr)_18rem] xl:min-h-0 xl:flex-1">
        <div className="relative w-full xl:h-full">
          <CatanBoardSvg layout={layout.data} observation={observation} />
        </div>
        <CatanPlayers observation={observation} match={context.match} pending={context.frame.pending} />
      </div>
    </div>
  );
}

export const catan = defineGame({
  schema: observationSchema,
  usesLayout: true,
  tabs: [{ id: "board", label: "Board", render: (observation, context) => <CatanBoard observation={observation} context={context} /> }],
  eventIcons: {
    started: Flag,
    board_prepared: MapIcon,
    setup_started: Flag,
    setup_turn: ArrowRight,
    setup_complete: CircleCheck,
    starting_resources: Gift,
    turn_started: Play,
    turn_ended: Square,
    dice_rolled: Dices,
    production: Wheat,
    seven_rolled: TriangleAlert,
    discard_notice: TriangleAlert,
    discarded: Trash2,
    robber_moved: VenetianMask,
    stolen: HandGrab,
    stole_card: HandGrab,
    card_stolen: HandGrab,
    road_built: Route,
    settlement_built: House,
    city_built: Building2,
    bank_trade: Landmark,
    offer_made: MessageSquare,
    offer_accepted: Handshake,
    offer_declined: ThumbsDown,
    dev_bought: Layers,
    dev_drawn: Layers,
    knight_played: Swords,
    monopoly_played: Coins,
    year_of_plenty_played: Sparkles,
    road_building_played: Construction,
    free_roads_exhausted: Construction,
    longest_road: Award,
    longest_road_lost: Award,
    largest_army: Shield,
    largest_army_lost: Shield,
    game_over: Trophy,
  },
});
