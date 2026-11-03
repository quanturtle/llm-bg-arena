"use client";

import { ChevronLeft, ChevronRight, Pause, Play, SkipBack, SkipForward, Timer } from "lucide-react";

import { SeatChip } from "@/components/seat";
import { ForfeitBadge, WinnerBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import type { Clocks } from "@/features/match/clocks";
import { SPEEDS, type ReplayAction, type ReplayState, type Speed } from "@/features/match/replay";
import type { MatchSummary, ScoreView } from "@/lib/api";
import { formatClock, seatName } from "@/lib/format";
import { cn } from "@/lib/utils";

// Radix selects take no empty value, so this stands for the spectator.
const SPECTATOR = "spectator";

function Transport({ state, dispatch }: { state: ReplayState; dispatch: React.Dispatch<ReplayAction> }) {
  return (
    <div className="flex items-center gap-1">
      <Button variant="ghost" size="icon-sm" title="First step (Home)" onClick={() => dispatch({ type: "seek", step: 0 })}>
        <SkipBack />
      </Button>
      <Button variant="ghost" size="icon-sm" title="Previous step (←)" onClick={() => dispatch({ type: "seekBy", delta: -1 })}>
        <ChevronLeft />
      </Button>
      <Button size="icon-sm" title="Play or pause (space)" onClick={() => dispatch({ type: "togglePlay" })}>
        {state.playing ? <Pause /> : <Play />}
      </Button>
      <Button variant="ghost" size="icon-sm" title="Next step (→)" onClick={() => dispatch({ type: "seekBy", delta: 1 })}>
        <ChevronRight />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        title="Last step (End)"
        onClick={() => dispatch({ type: "seek", step: Number.POSITIVE_INFINITY })}
      >
        <SkipForward />
      </Button>
    </div>
  );
}

/**
 * Each seat with its points at the step on screen and its clock; a pulsing dot in a slot of its
 * own marks the players thinking.
 */
function SeatClocks({ match, clocks, scores }: { match: MatchSummary; clocks: Clocks; scores: ScoreView[] }) {
  const finished = match.status === "finished";
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
      <span className="flex items-center gap-1.5 text-muted-foreground" title="Time since the match began">
        <Timer className="size-4" />
        <span className="w-[7ch] font-mono text-foreground tabular-nums">{formatClock(clocks.matchMs)}</span>
      </span>
      {match.seats.map((seat) => {
        const clock = clocks.seats[seat.player];
        const points = scores.find((score) => score.player === seat.player)?.points;
        return (
          <span key={seat.player} className="flex min-w-0 items-center gap-2" title={`Time ${seatName(seat)} has spent on its moves`}>
            <SeatChip seat={seat} className="max-w-64" />
            {finished && seat.rank === 1 ? <WinnerBadge /> : seat.forfeited ? <ForfeitBadge /> : null}
            {/* wide enough for two-digit points, since a flex item never shrinks below its content */}
            <span className="w-[8ch] shrink-0 text-right whitespace-nowrap tabular-nums" title="Points others can see at this step">
              <strong>{points ?? ""}</strong> <span className="text-xs text-muted-foreground">pts</span>
            </span>
            <span className={cn("w-[7ch] font-mono tabular-nums", clock.thinking ? "font-semibold text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
              {formatClock(clock.ms)}
            </span>
            <span
              aria-label={clock.thinking ? "thinking" : undefined}
              className={cn("size-2 rounded-full", clock.thinking ? "animate-pulse bg-amber-500" : "bg-transparent")}
            />
          </span>
        );
      })}
    </div>
  );
}

/** Replay controls on one row and the clocks on the next; every slot keeps its width as steps change. */
export function ReplayBar({
  match,
  state,
  dispatch,
  clocks,
  scores,
}: {
  match: MatchSummary;
  state: ReplayState;
  dispatch: React.Dispatch<ReplayAction>;
  clocks: Clocks;
  scores: ScoreView[];
}) {
  const digits = String(state.last).length;
  return (
    <section aria-label="Replay controls" className="flex flex-col gap-2 rounded-xl border bg-card/95 px-4 py-2.5 shadow-xs backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Transport state={state} dispatch={dispatch} />
        <Select value={String(state.speed)} onValueChange={(value) => dispatch({ type: "setSpeed", speed: Number(value) as Speed })}>
          <SelectTrigger size="sm" className="w-20" title="Playback speed">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SPEEDS.map((speed) => (
              <SelectItem key={speed} value={String(speed)}>
                {speed}×
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Slider
          className="min-w-40 flex-1"
          min={0}
          max={Math.max(state.last, 1)}
          step={1}
          value={[state.step]}
          aria-label="Step"
          onValueChange={([step]) => dispatch({ type: "seek", step })}
        />
        <span className="shrink-0 text-right font-mono text-sm tabular-nums" style={{ width: `${2 * digits + 9}ch` }}>
          step {state.step} / {state.last}
        </span>
        <div className="flex items-center gap-2">
          <Label className="text-muted-foreground">View</Label>
          <Select
            value={state.viewer === null ? SPECTATOR : String(state.viewer)}
            onValueChange={(value) => dispatch({ type: "setViewer", viewer: value === SPECTATOR ? null : Number(value) })}
          >
            <SelectTrigger size="sm" className="w-52">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SPECTATOR}>Spectator</SelectItem>
              {match.seats.map((seat) => (
                <SelectItem key={seat.player} value={String(seat.player)}>
                  P{seat.player + 1} {seatName(seat)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Label className="flex items-center gap-2 text-muted-foreground">
          <Switch checked={state.omniscient} onCheckedChange={(omniscient) => dispatch({ type: "setOmniscient", omniscient })} />
          All events
        </Label>
      </div>
      <SeatClocks match={match} clocks={clocks} scores={scores} />
    </section>
  );
}
