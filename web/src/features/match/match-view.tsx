"use client";

import { useSearchParams } from "next/navigation";

import { ErrorAlert, LoadingRows } from "@/components/page";
import { Card, CardContent } from "@/components/ui/card";
import { clocksAt } from "@/features/match/clocks";
import { MatchHeader } from "@/features/match/match-header";
import { liveState } from "@/features/match/replay";
import { ReplayBar } from "@/features/match/replay-bar";
import { useFrame, useLaunch, useTimeline } from "@/features/match/use-match-data";
import { useReplay } from "@/features/match/use-replay";
import { useNow } from "@/hooks/use-now";
import type { Outline } from "@/lib/api";

function numberParam(value: string | null): number | null {
  return value === null || value === "" || Number.isNaN(Number(value)) ? null : Number(value);
}

function MatchReplay({ matchId, outline }: { matchId: string; outline: Outline }) {
  const params = useSearchParams();
  const [state, dispatch] = useReplay(matchId, outline, {
    step: numberParam(params.get("step")),
    viewer: numberParam(params.get("viewer")),
    omniscient: params.get("all") === "1",
  });
  const launch = useLaunch(matchId, state.running).data ?? null;
  const frame = useFrame(matchId, state.step, state.last);
  const live = liveState(state, launch?.status ?? null);
  const now = useNow(state.running);
  const clocks = clocksAt(outline, state.step, frame.data?.pending ?? [], live === "on", now);
  const board = frame.data?.boards.find((view) => view.viewer === state.viewer) ?? frame.data?.boards[0];
  return (
    <>
      <MatchHeader outline={outline} launch={launch} live={live} />
      <div className="sticky top-14 z-30 -mx-1 mb-4 px-1 pt-1">
        <ReplayBar match={outline.match} state={state} dispatch={dispatch} clocks={clocks} />
      </div>
      {frame.error ? <ErrorAlert error={frame.error} /> : null}
      <Card>
        <CardContent>
          <pre className="overflow-x-auto font-mono text-xs leading-relaxed">{board?.text}</pre>
        </CardContent>
      </Card>
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
