"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, Play, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useReducer } from "react";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  currentGame,
  formReducer,
  GAME_OPTIONS,
  humanize,
  initialFormState,
  matchConfig,
  modelName,
  playerRange,
  summaryText,
  type FormAction,
  type FormState,
} from "@/features/new-match/form-model";
import { SeatCard } from "@/features/new-match/seat-card";
import { matchHref } from "@/features/matches/match-table";
import { api, type Launch, type MatchOptions } from "@/lib/api";
import { cn } from "@/lib/utils";

// a blank seed becomes a random one below this bound
const SEED_RANGE = 1_000_000;

function Step({ number, title, aside, children }: { number: number; title: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">
          <span className="mr-2 text-muted-foreground tabular-nums">{number}.</span>
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function GamePicker({ state, dispatch }: { state: FormState; dispatch: React.Dispatch<FormAction> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {state.options.games.map((game) => (
        <button
          key={game.id}
          type="button"
          onClick={() => dispatch({ type: "chooseGame", game: game.id })}
          className={cn(
            "flex flex-col items-start gap-1 rounded-xl border bg-card p-4 text-left transition-colors hover:border-foreground/30",
            game.id === state.game && "border-foreground ring-1 ring-foreground",
          )}
        >
          <span className="font-semibold">{game.name}</span>
          <span className="text-sm text-muted-foreground">{game.summary}</span>
          <span className="text-xs">{playerRange(game.player_counts)}</span>
        </button>
      ))}
    </div>
  );
}

function GameOptions({ state, dispatch }: { state: FormState; dispatch: React.Dispatch<FormAction> }) {
  const game = currentGame(state);
  const entries = Object.entries(game.settings);
  if (!entries.length) return null;
  return (
    <Card className="mt-4">
      <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {entries.map(([key, defaultValue]) => {
          const meta = GAME_OPTIONS[`${game.id}.${key}`] ?? { label: humanize(key) };
          const value = state.settings[key];
          const set = (next: string | number | boolean | undefined) => dispatch({ type: "setGameSetting", key, value: next });
          if (typeof defaultValue === "boolean") {
            return (
              <div key={key} className="flex flex-col gap-1.5">
                <Label>{meta.label}</Label>
                <Switch checked={value === undefined ? defaultValue : Boolean(value)} onCheckedChange={set} />
                {meta.hint ? <p className="text-xs text-muted-foreground">{meta.hint}</p> : null}
              </div>
            );
          }
          const numeric = typeof defaultValue === "number" || defaultValue === null;
          return (
            <div key={key} className="flex flex-col gap-1.5">
              <Label>{meta.label}</Label>
              <Input
                type={numeric ? "number" : "text"}
                min={meta.min}
                max={meta.max}
                placeholder={defaultValue === null ? "none" : `default: ${String(defaultValue)}`}
                value={value === undefined ? "" : String(value)}
                onChange={(event) => {
                  const raw = event.target.value;
                  set(raw === "" ? undefined : numeric ? Number(raw) : raw);
                }}
              />
              {meta.hint ? <p className="text-xs text-muted-foreground">{meta.hint}</p> : null}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function SameModel({ state, dispatch }: { state: FormState; dispatch: React.Dispatch<FormAction> }) {
  return (
    <Select value="" onValueChange={(model) => dispatch({ type: "sameModel", model })}>
      <SelectTrigger className="w-64">
        <SelectValue placeholder="Give everyone the same model…" />
      </SelectTrigger>
      <SelectContent>
        {state.options.models.map((id) => (
          <SelectItem key={id} value={id}>
            {modelName(id)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function StartPanel({ state, dispatch }: { state: FormState; dispatch: React.Dispatch<FormAction> }) {
  const router = useRouter();
  const start = useMutation({
    mutationFn: () => {
      const seed = state.seed === "" ? Math.floor(Math.random() * SEED_RANGE) : Number(state.seed);
      // JSON is valid YAML, so the config goes as JSON text
      return api.startMatch(JSON.stringify(matchConfig(state, seed), null, 2));
    },
    onSuccess: (launch) => router.push(matchHref(launch.match_id)),
  });
  const preview = JSON.stringify(matchConfig(state, state.seed === "" ? "(random)" : Number(state.seed)), null, 2);
  return (
    <Card>
      <CardContent className="flex flex-col items-start gap-4">
        <p className="text-sm">{summaryText(state)}</p>
        <Button size="lg" disabled={start.isPending} onClick={() => start.mutate()}>
          <Play /> Start match
        </Button>
        {start.error ? <ErrorAlert error={start.error} title="The match did not start" /> : null}
        <Collapsible className="w-full">
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="group -ml-2 text-muted-foreground">
              <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
              More options
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 flex flex-col gap-3">
            <div className="flex max-w-sm flex-col gap-1.5">
              <Label>Seed</Label>
              <Input
                type="number"
                placeholder="random each time"
                value={state.seed}
                onChange={(event) => dispatch({ type: "setSeed", seed: event.target.value })}
              />
              <p className="text-xs text-muted-foreground">The same seed deals the same board; leave empty for a new one.</p>
            </div>
            <p className="text-xs text-muted-foreground">Config sent to the server:</p>
            <pre className="max-h-80 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs">{preview}</pre>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}

function LaunchList({ launches }: { launches: Launch[] }) {
  if (!launches.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Started from here</CardTitle>
        <CardDescription>Matches this server started, newest first.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2 text-sm">
          {launches.map((launch) => (
            <li key={launch.match_id} className="flex flex-wrap items-center gap-2">
              <Link href={matchHref(launch.match_id)} className="font-mono hover:underline">
                {launch.match_id}
              </Link>
              <StatusBadge status={launch.status} />
              {launch.error ? <span className="text-destructive">{launch.error}</span> : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function NewMatchForm({ options, launches }: { options: MatchOptions; launches: Launch[] }) {
  const [state, dispatch] = useReducer(formReducer, options, initialFormState);
  const counts = currentGame(state).player_counts;
  const most = counts[counts.length - 1];
  const full = state.seats.length >= most;
  // a typed model id is looked up once; its settings then follow what it accepts
  const lookUp = async (model: string) => {
    if (!model || model in state.capabilities || model in state.unknown) {
      dispatch({ type: "modelLookedUp", model, capabilities: null, error: null });
      return;
    }
    try {
      dispatch({ type: "modelLookedUp", model, capabilities: await api.modelCapabilities(model), error: null });
    } catch (error) {
      dispatch({ type: "modelLookedUp", model, capabilities: null, error: error instanceof Error ? error.message : String(error) });
    }
  };
  return (
    <>
      <Step number={1} title="Game">
        <GamePicker state={state} dispatch={dispatch} />
        <GameOptions state={state} dispatch={dispatch} />
      </Step>
      <Step
        number={2}
        title="Players"
        aside={
          <>
            <span className="text-sm text-muted-foreground">
              {state.seats.length} ({playerRange(counts).replace(" players", "")} allowed)
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={full}
              title={full ? `${currentGame(state).name} seats at most ${most} players` : ""}
              onClick={() => dispatch({ type: "addSeat" })}
            >
              <Plus /> Add player
            </Button>
            <SameModel state={state} dispatch={dispatch} />
          </>
        }
      >
        {state.options.catalog_error ? (
          <p className="mb-3 text-sm text-muted-foreground">
            OpenRouter&apos;s model details could not be loaded, so every setting is offered: {state.options.catalog_error}
          </p>
        ) : null}
        <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {state.seats.map((seat, index) => (
            <SeatCard key={seat.id} state={state} seat={seat} index={index} dispatch={dispatch} onTyped={lookUp} />
          ))}
        </div>
      </Step>
      <Step number={3} title="Start">
        <div className="grid items-start gap-4 lg:grid-cols-2">
          <StartPanel state={state} dispatch={dispatch} />
          <LaunchList launches={launches} />
        </div>
      </Step>
    </>
  );
}

export function NewMatchView() {
  const options = useQuery({ queryKey: ["match-options"], queryFn: api.matchOptions, staleTime: Infinity });
  const launches = useQuery({ queryKey: ["launches"], queryFn: api.launches });
  return (
    <>
      <PageTitle title="New match" description="Choose a game, then who plays it. Every player is a language model through OpenRouter." />
      {options.error ? <ErrorAlert error={options.error} /> : null}
      {options.data ? <NewMatchForm options={options.data} launches={launches.data ?? []} /> : options.isPending ? <LoadingRows /> : null}
    </>
  );
}
