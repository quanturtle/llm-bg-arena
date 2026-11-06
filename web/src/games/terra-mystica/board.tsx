import {
  ArrowUpRight,
  Castle,
  Church,
  Coins,
  Crown,
  Flag,
  Gift,
  Hammer,
  House,
  Pickaxe,
  RotateCcw,
  Ship,
  Shovel,
  SkipForward,
  Sparkles,
  Target,
  Trophy,
  Users,
  Zap,
} from "lucide-react";

import { StatusBar } from "@/components/board-parts";
import { SeatChip } from "@/components/seat";
import { defineGame, type BoardContext } from "@/games/define";
import { TerraMysticaBoardSvg, TerrainLegend } from "@/games/terra-mystica/board-svg";
import { TerraMysticaCults } from "@/games/terra-mystica/cults";
import type { CultBonus, TerraMysticaObservation } from "@/games/terra-mystica/observation";
import { observationSchema } from "@/games/terra-mystica/observation";
import { TerraMysticaPlayers } from "@/games/terra-mystica/players";
import type { MatchSummary } from "@/lib/api";

function titleCase(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function bonusText(bonus: CultBonus): string {
  const singular: Record<string, string> = { priests: "priest", workers: "worker", coins: "coin", power: "power", spades: "spade" };
  const reward = bonus.amount === 1 ? (singular[bonus.reward] ?? bonus.reward) : bonus.reward;
  return `${bonus.amount} ${reward} per ${bonus.per} ${bonus.cult}`;
}

function TerraMysticaStatus({ observation, match }: { observation: TerraMysticaObservation; match: MatchSummary }) {
  if (observation.game_over) {
    const final = observation.final_scores ?? [];
    const best = final.length ? Math.max(...final.map((score) => score.points)) : null;
    const winners = best === null ? [] : final.filter((score) => score.points === best).map((score) => score.player);
    return (
      <StatusBar tone="done">
        <Trophy className="size-4 shrink-0" />
        {winners.length ? (
          <>
            Game over:
            {winners.map((player, index) => (
              <span key={player} className="flex items-center gap-1">
                {index > 0 ? (index === winners.length - 1 ? " and " : ", ") : null}
                <SeatChip seat={match.seats[player]} link={false} className="min-w-0" />
              </span>
            ))}
            {winners.length > 1 ? "shared the win" : "won"}
          </>
        ) : (
          "Game over"
        )}
        {observation.end_reason ? <span className="truncate font-normal">({observation.end_reason})</span> : null}
      </StatusBar>
    );
  }
  const active = match.seats[observation.active];
  const scoring = observation.scoring[observation.round - 1];
  const bonus = observation.scoring_bonuses[observation.round - 1];
  return (
    <StatusBar
      aside={
        scoring ? (
          <span className="text-xs text-muted-foreground" title={bonus ? `This round scores ${titleCase(scoring).toLowerCase()}; ${bonusText(bonus)}` : undefined}>
            scores <span className="font-medium text-foreground">{titleCase(scoring).toLowerCase()}</span>
            {bonus ? <span className="hidden @2xl:inline"> · {bonusText(bonus)}</span> : null}
          </span>
        ) : null
      }
    >
      <span className="font-semibold tabular-nums">Round {observation.round}</span>
      <span className="text-muted-foreground">·</span>
      <span className="truncate text-muted-foreground">{titleCase(observation.phase).toLowerCase()}</span>
      {active ? (
        <>
          <span className="text-muted-foreground">·</span>
          <SeatChip seat={active} link={false} className="min-w-0" />
          <span className="shrink-0 text-muted-foreground">to act</span>
        </>
      ) : null}
    </StatusBar>
  );
}

// Wide boards put the players beside the map; narrow ones stack them below it. On desktop the
// map shrinks to the panel's height, so the whole board shows without scrolling.
function TerraMysticaBoard({ observation, context }: { observation: TerraMysticaObservation; context: BoardContext }) {
  return (
    <div className="@container flex flex-col gap-3 xl:h-full">
      <TerraMysticaStatus observation={observation} match={context.match} />
      <div className="grid gap-4 @3xl:grid-cols-[minmax(0,1fr)_19rem] xl:min-h-0 xl:flex-1">
        <div className="flex min-w-0 flex-col gap-2 xl:min-h-0">
          <div className="relative mx-auto w-full max-w-[880px] xl:min-h-0 xl:flex-1">
            <TerraMysticaBoardSvg observation={observation} events={context.frame.events} />
          </div>
          <TerrainLegend />
        </div>
        <TerraMysticaPlayers observation={observation} match={context.match} />
      </div>
    </div>
  );
}

export const terraMystica = defineGame({
  schema: observationSchema,
  usesLayout: false,
  tabs: [
    { id: "board", label: "Board", render: (observation, context) => <TerraMysticaBoard observation={observation} context={context} /> },
    { id: "cults", label: "Cults", render: (observation) => <TerraMysticaCults observation={observation} /> },
  ],
  eventIcons: {
    game_started: Flag,
    factions: Users,
    scoring_tiles: Target,
    setup_dwelling: House,
    dwelling_placed: House,
    round_started: RotateCcw,
    income: Coins,
    built: Hammer,
    upgraded: ArrowUpRight,
    transformed: Pickaxe,
    passed: SkipForward,
    priest_sent: Church,
    cult_advanced: ArrowUpRight,
    cult_bonus: Sparkles,
    cult_spade_used: Pickaxe,
    cult_spade_skipped: SkipForward,
    shipping_advanced: Ship,
    digging_advanced: Shovel,
    power_action: Zap,
    town_founded: Castle,
    town_tile: Crown,
    stronghold_convert: Castle,
    stronghold_reward: Gift,
    alchemist_trade: Coins,
    game_over: Trophy,
  },
});
