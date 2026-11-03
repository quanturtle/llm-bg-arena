"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { ErrorAlert, LoadingRows } from "@/components/page";
import { BoardPanel } from "@/features/match/board-panel";
import { clocksAt } from "@/features/match/clocks";
import { DecisionCard, type DecisionTab } from "@/features/match/decision-card";
import { EventLog } from "@/features/match/event-log";
import { MatchHeader } from "@/features/match/match-header";
import { PointsChart } from "@/features/match/points-chart";
import { liveState } from "@/features/match/replay";
import { ReplayBar } from "@/features/match/replay-bar";
import { useFrame, useLaunch, useLayout, useTimeline } from "@/features/match/use-match-data";
import { useReplay } from "@/features/match/use-replay";
import { GAMES } from "@/games/registry";
import { useFillViewport } from "@/hooks/use-fill-viewport";
import { useHeight } from "@/hooks/use-height";
import { useNow } from "@/hooks/use-now";
import type { Outline } from "@/lib/api";

// the site header's height (h-14) and the gaps around the replay bar, in px
const SITE_HEADER_PX = 56;
const BAR_GAP_PX = 16;
// from Tailwind's xl breakpoint the side column sticks and fills the window down to this gap
const WIDE_SCREEN = "(min-width: 80rem)";
const SIDE_GAP_PX = 16;

function numberParam(value: string | null): number | null {
  return value === null || value === "" || Number.isNaN(Number(value)) ? null : Number(value);
}

/**
 * The replay page. The replay bar sticks under the site header; on wide screens the decision card
 * and the event log stick beside the board at fixed heights, so stepping never moves them.
 */
function MatchReplay({ matchId, outline }: { matchId: string; outline: Outline }) {
  const params = useSearchParams();
  const [state, dispatch] = useReplay(matchId, outline, {
    step: numberParam(params.get("step")),
    viewer: numberParam(params.get("viewer")),
    omniscient: params.get("all") === "1",
  });
  const [boardTab, setBoardTab] = useState("board");
  const [decisionTab, setDecisionTab] = useState<DecisionTab>("reasoning");
  const [barRef, barHeight] = useHeight<HTMLDivElement>();
  const sideRef = useFillViewport<HTMLDivElement>(WIDE_SCREEN, SIDE_GAP_PX);
  const match = outline.match;
  const launch = useLaunch(matchId, state.running).data ?? null;
  const layout = useLayout(match.game_id).data ?? null;
  const frame = useFrame(matchId, state.step, state.last);
  const live = liveState(state, launch?.status ?? null);
  const now = useNow(state.running);
  const clocks = clocksAt(outline, state.step, frame.data?.pending ?? [], live === "on", now);
  const sideTop = SITE_HEADER_PX + barHeight + BAR_GAP_PX;
  return (
    <>
      <MatchHeader outline={outline} launch={launch} live={live} />
      <div ref={barRef} className="sticky top-14 z-30 -mx-1 bg-background px-1 pt-1 pb-3">
        <ReplayBar match={match} state={state} dispatch={dispatch} clocks={clocks} />
      </div>
      {frame.error ? <ErrorAlert error={frame.error} /> : null}
      {frame.data ? (
        <div
          className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_26rem] 2xl:grid-cols-[minmax(0,1fr)_30rem]"
          style={{ "--side-top": `${sideTop}px` } as React.CSSProperties}
        >
          <div className="flex min-w-0 flex-col gap-4">
            <BoardPanel
              match={match}
              frame={frame.data}
              viewer={state.viewer}
              layout={layout}
              tab={boardTab}
              onTab={setBoardTab}
              isFinal={match.status === "finished" && state.step === state.last}
            />
            <PointsChart outline={outline} step={state.step} onSeek={(step) => dispatch({ type: "seek", step })} />
          </div>
          <div ref={sideRef} className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-(--side-top) xl:self-start">
            <DecisionCard match={match} frame={frame.data} tab={decisionTab} onTab={setDecisionTab} className="h-88 shrink-0" />
            <EventLog
              outline={outline}
              step={state.step}
              viewer={state.viewer}
              omniscient={state.omniscient}
              icons={GAMES[match.game_id]?.eventIcons ?? {}}
              className="h-112 xl:h-auto xl:min-h-40 xl:flex-1"
            />
          </div>
        </div>
      ) : (
        <LoadingRows />
      )}
    </>
  );
}

export function MatchView() {
  const matchId = useSearchParams().get("id") ?? "";
  const timeline = useTimeline(matchId);
  if (!matchId) return <ErrorAlert error="No match named in the address." />;
  // a failed poll of a running match keeps the outline it has
  if (!timeline.data) return timeline.error ? <ErrorAlert error={timeline.error} /> : <LoadingRows />;
  return <MatchReplay key={matchId} matchId={matchId} outline={timeline.data} />;
}
