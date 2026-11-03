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
import { useNow } from "@/hooks/use-now";
import type { Outline } from "@/lib/api";

function numberParam(value: string | null): number | null {
  return value === null || value === "" || Number.isNaN(Number(value)) ? null : Number(value);
}

/**
 * The replay page. On desktop it is exactly one window tall: the header and the replay bar on top,
 * then the board and a side column (decision card over the event log) sharing the rest; a panel
 * whose content is taller scrolls inside itself. Narrower screens stack the panels and scroll.
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
  const match = outline.match;
  const launch = useLaunch(matchId, state.running).data ?? null;
  const layout = useLayout(match.game_id).data ?? null;
  const frame = useFrame(matchId, state.step, state.last);
  const live = liveState(state, launch?.status ?? null);
  const now = useNow(state.running);
  const clocks = clocksAt(outline, state.step, frame.data?.pending ?? [], live === "on", now);
  return (
    // 6.5rem is the site header (h-14) plus the main element's vertical padding (py-6)
    <div className="flex flex-col gap-3 xl:h-[calc(100dvh-6.5rem)]">
      <MatchHeader outline={outline} launch={launch} live={live} />
      <div className="sticky top-14 z-30 -mx-1 bg-background px-1 pt-1 xl:static">
        <ReplayBar match={match} state={state} dispatch={dispatch} clocks={clocks} scores={frame.data?.scores ?? []} />
      </div>
      {frame.error ? <ErrorAlert error={frame.error} /> : null}
      {frame.data ? (
        <div className="grid grid-cols-1 gap-3 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_22rem] 2xl:grid-cols-[minmax(0,1fr)_26rem]">
          <BoardPanel
            match={match}
            frame={frame.data}
            viewer={state.viewer}
            layout={layout}
            tab={boardTab}
            onTab={setBoardTab}
            points={<PointsChart outline={outline} step={state.step} onSeek={(step) => dispatch({ type: "seek", step })} />}
            className="min-w-0 xl:min-h-0"
          />
          <div className="flex min-w-0 flex-col gap-3 xl:min-h-0">
            <DecisionCard
              match={match}
              frame={frame.data}
              tab={decisionTab}
              onTab={setDecisionTab}
              className="h-88 shrink-0 xl:h-[min(22rem,45%)]"
            />
            <EventLog
              outline={outline}
              step={state.step}
              viewer={state.viewer}
              omniscient={state.omniscient}
              icons={GAMES[match.game_id]?.eventIcons ?? {}}
              className="h-112 xl:h-auto xl:min-h-0 xl:flex-1"
            />
          </div>
        </div>
      ) : (
        <LoadingRows />
      )}
    </div>
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
