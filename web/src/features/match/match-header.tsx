"use client";

import { CircleAlert, Pause, Play, Square, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { LiveIndicator, StatusBadge, type ShownStatus } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DeleteMatchButton } from "@/features/matches/delete-match-button";
import { useLaunchControl } from "@/features/match/use-match-data";
import type { Launch, Outline } from "@/lib/api";
import { promptLabel } from "@/lib/format";

/** The launcher knows a match is paused or failed; its log only says running or stopped. */
export function shownStatus(outline: Outline, launch: Launch | null): ShownStatus {
  const status = outline.match.status;
  return launch && (status === "running" || launch.status === "failed") ? launch.status : status;
}

function LiveControls({ matchId, launch }: { matchId: string; launch: Launch }) {
  const control = useLaunchControl(matchId);
  const paused = launch.status === "paused";
  return (
    <>
      {paused ? (
        <Button size="sm" disabled={control.isPending} onClick={() => control.mutate("resume")}>
          <Play /> Resume
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={control.isPending}
          title="Holds the match before its next round; a model call in progress finishes first."
          onClick={() => control.mutate("pause")}
        >
          <Pause /> Pause
        </Button>
      )}
      <Button
        size="sm"
        variant="destructive"
        disabled={control.isPending}
        title="Ends the match now; it cannot be resumed. Its log is kept."
        onClick={() => control.mutate("stop")}
      >
        <Square /> Stop
      </Button>
    </>
  );
}

/** Game, id, status and settings on the left; pause, resume, stop or delete on the right. */
export function MatchHeader({ outline, launch, live }: { outline: Outline; launch: Launch | null; live: "on" | "off" | null }) {
  const router = useRouter();
  const match = outline.match;
  const config = Object.entries(match.config)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(" ");
  const meta = `seed ${match.seed} · ${config} · ${promptLabel(match.prompt_version)}`;
  const playing = launch !== null && (launch.status === "running" || launch.status === "paused");
  return (
    <div className="flex flex-col gap-3">
      {/* one line: the settings truncate first, so the title and the buttons keep their places */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-xl font-semibold tracking-tight">
          <Link href={`/game?id=${encodeURIComponent(match.game_id)}`} className="hover:underline">
            {match.game_id}
          </Link>
        </h1>
        <span className="font-mono text-sm text-muted-foreground">{match.match_id}</span>
        <StatusBadge status={shownStatus(outline, launch)} />
        {live ? <LiveIndicator on={live === "on"} /> : null}
        <Tooltip>
          <TooltipTrigger asChild>
            <p className="min-w-0 flex-1 basis-48 truncate font-mono text-xs text-muted-foreground">{meta}</p>
          </TooltipTrigger>
          <TooltipContent className="max-w-xl font-mono">{meta}</TooltipContent>
        </Tooltip>
        <div className="ml-auto flex items-center gap-2">
          {playing ? (
            <LiveControls matchId={match.match_id} launch={launch} />
          ) : (
            <DeleteMatchButton
              matchId={match.match_id}
              onDeleted={() => router.push("/matches")}
              trigger={
                <Button size="sm" variant="outline" title="Removes this match's log and thoughts file.">
                  <Trash2 /> Delete
                </Button>
              }
            />
          )}
        </div>
      </div>
      {launch?.error ? (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>This match failed</AlertTitle>
          <AlertDescription>{launch.error}</AlertDescription>
        </Alert>
      ) : null}
      {outline.replay_error ? (
        <Alert>
          <CircleAlert />
          <AlertTitle>Only steps 0–{outline.frame_count - 1} can be shown</AlertTitle>
          <AlertDescription>
            This log stops matching the current {match.game_id} rules after that, probably because the rules changed after it was recorded.{" "}
            {outline.replay_error}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
