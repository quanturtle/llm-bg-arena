"use client";

import { Brain, NotebookPen, OctagonX, type LucideIcon } from "lucide-react";

import { SeatChip } from "@/components/seat";
import { ForfeitBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Frame, MatchSummary, TraceRecord } from "@/lib/api";
import { formatCost, formatSeconds } from "@/lib/format";
import { cn } from "@/lib/utils";

type Rejected = { answer: string | null; reason: string };

// A rejected attempt records the answer and why the game refused it.
function rejectedAttempts(trace: TraceRecord): Rejected[] {
  return trace.attempts.flatMap((attempt) => {
    const rejection = attempt.rejection as { kind?: string; feedback?: string } | null | undefined;
    if (!rejection) return [];
    const answer = attempt.answer === undefined || attempt.answer === null ? null : String(attempt.answer);
    return [{ answer, reason: `${rejection.kind ?? "rejected"}: ${rejection.feedback ?? ""}` }];
  });
}

/** What the card shows for one step: the decision that made it, or the forfeit. */
type Shown = {
  player: number;
  headline: React.ReactNode;
  did: string;
  asked: string;
  took: string;
  fallback: string | null;
  trace: TraceRecord;
};

function shownAt(frame: Frame): Shown | null {
  const decision = frame.decision;
  if (decision) {
    const trace = decision.trace;
    const tokens = trace.prompt_tokens + trace.completion_tokens;
    return {
      player: decision.player,
      headline: <code className="truncate font-mono text-sm">{decision.action}</code>,
      did: decision.description,
      asked: decision.prompt,
      took: `${formatSeconds(decision.latency_seconds)}${tokens ? `, ${tokens.toLocaleString()} tokens, ${formatCost(trace.cost_usd)}` : ""}`,
      fallback: trace.fallback,
      trace,
    };
  }
  const forfeit = frame.forfeits[0];
  if (!forfeit) return null;
  return {
    player: forfeit.player,
    headline: <ForfeitBadge />,
    did: forfeit.reason,
    asked: "",
    took: formatSeconds(forfeit.latency_seconds),
    fallback: null,
    trace: forfeit.trace,
  };
}

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[3.5rem_minmax(0,1fr)] gap-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate">{children}</dd>
    </div>
  );
}

// A titled text box that scrolls inside its share of the card.
function TextPane({ icon: Icon, title, text, empty, className }: { icon: LucideIcon; title: string; text: string | null; empty: string; className?: string }) {
  return (
    <section aria-label={title} className={cn("flex min-h-0 flex-col gap-1.5 px-4", className)}>
      <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Icon className="size-3.5" /> {title}
      </h3>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-lg border bg-muted/40 px-3 py-2">
        {text ? (
          <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap">{text}</pre>
        ) : (
          <p className="text-xs text-muted-foreground">{empty}</p>
        )}
      </div>
    </section>
  );
}

// One line of fixed height; the rejected answers open in a popover when there are any.
function RejectedLine({ rejected }: { rejected: Rejected[] }) {
  const label = (
    <>
      <OctagonX className="size-3.5" /> Rejected answers <span className="tabular-nums">{rejected.length}</span>
    </>
  );
  if (!rejected.length) return <p className="flex h-6 items-center gap-1.5 px-4 text-xs text-muted-foreground">{label}</p>;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="xs" className="mx-3 h-6 w-fit text-amber-600 dark:text-amber-400">
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex max-h-80 w-96 flex-col gap-2 overflow-y-auto">
        {rejected.map((attempt, index) => (
          <div key={index} className="border-l-2 border-amber-500 pl-2 text-xs">
            {attempt.answer ? <div className="font-mono">{attempt.answer}</div> : null}
            <div className="text-muted-foreground">{attempt.reason}</div>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  );
}

/**
 * The decision behind the step on screen, in a card of fixed height: the header lines truncate,
 * the reasoning and the notes show together and scroll inside their own boxes, so nothing moves.
 */
export function DecisionCard({ match, frame, className }: { match: MatchSummary; frame: Frame; className?: string }) {
  const shown = shownAt(frame);
  const rejected = shown ? rejectedAttempts(shown.trace) : [];
  const seat = shown ? match.seats[shown.player] : null;
  const waiting = frame.pending.map((player) => `P${player + 1}`).join(", ");
  return (
    <Card aria-label="Decision" className={cn("gap-2.5 pt-4 pb-2", className)}>
      <div className="flex h-6 min-w-0 items-center gap-2 px-4">
        {seat ? <SeatChip seat={seat} className="min-w-0 max-w-[60%]" /> : <span className="font-medium">Setup</span>}
        <span className="flex min-w-0 items-center">{shown?.headline}</span>
        {shown?.fallback ? (
          <Badge variant="outline" className="ml-auto border-amber-500/50 text-amber-600 dark:text-amber-400">
            fallback: {shown.fallback}
          </Badge>
        ) : null}
      </div>
      <dl className="flex flex-col gap-1 px-4">
        <Line label="Did">{shown ? shown.did : waiting ? `Waiting for ${waiting}.` : "No decision yet."}</Line>
        <Line label="Asked">
          {shown?.asked ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground">{shown.asked}</span>
              </TooltipTrigger>
              <TooltipContent className="max-w-md">{shown.asked}</TooltipContent>
            </Tooltip>
          ) : null}
        </Line>
        <Line label="Took">{shown?.took}</Line>
      </dl>
      <TextPane icon={Brain} title="Reasoning" text={shown?.trace.reasoning ?? null} empty="No reasoning at this step." className="flex-[3]" />
      <TextPane icon={NotebookPen} title="Notes kept" text={shown?.trace.memory ?? null} empty="No notes kept at this step." className="flex-[2]" />
      <RejectedLine rejected={rejected} />
    </Card>
  );
}
