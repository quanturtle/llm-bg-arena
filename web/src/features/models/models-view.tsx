"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, Trash2 } from "lucide-react";
import { useReducer, useState } from "react";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { ProviderLogo } from "@/components/provider-logo";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { configBrief, formReducer, humanize, initialFormState, seatEntry, suggestedConfigName } from "@/features/new-match/form-model";
import { SeatModel, SeatSettings } from "@/features/new-match/seat-card";
import { useModelLookup } from "@/features/new-match/use-model-lookup";
import { api, type MatchOptions, type ModelConfig, type SavedModelConfig } from "@/lib/api";

// shown by `configBrief`, so left out of the list of other settings
const BRIEF_KEYS = ["model", "reasoning", "reasoning_effort", "thinking_budget_tokens", "verbosity"];

/** The settings a config sets beyond its model and reasoning, as "Key: value" text. */
function otherSettings(config: ModelConfig): string {
  return Object.entries(config)
    .filter(([key, value]) => value !== null && value !== undefined && !BRIEF_KEYS.includes(key))
    .map(([key, value]) => `${humanize(key)}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join(" · ");
}

function useConfigsChanged() {
  const queryClient = useQueryClient();
  // the new-match form lists the saved configs from its options
  return () => Promise.all([queryClient.invalidateQueries({ queryKey: ["model-configs"] }), queryClient.invalidateQueries({ queryKey: ["match-options"] })]);
}

/** A name, a model and its settings, saved as a new config. */
function NewConfigForm({ options }: { options: MatchOptions }) {
  const [state, dispatch] = useReducer(formReducer, options, initialFormState);
  const [name, setName] = useState("");
  const lookUp = useModelLookup(state, dispatch);
  const changed = useConfigsChanged();
  // the form edits the first seat of a match form, which carries every model setting
  const seat = state.seats[0];
  const config = seatEntry(state, seat);
  const suggested = suggestedConfigName(config);
  const save = useMutation({
    mutationFn: () => api.saveModelConfig(name.trim() || suggested, config),
    onSuccess: async () => {
      setName("");
      await changed();
    },
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>New config</CardTitle>
        <CardDescription>A saved config never changes; to try other settings, save them under another name.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <SeatModel state={state} seat={seat} index={0} dispatch={dispatch} onTyped={lookUp} />
        <SeatSettings state={state} seat={seat} index={0} dispatch={dispatch} omit={["label"]} />
        <div className="flex flex-col gap-1.5">
          <Label>Name</Label>
          <Input value={name} placeholder={suggested} onChange={(event) => setName(event.target.value)} />
          <p className="text-xs text-muted-foreground">Its name on the leaderboard: lowercase letters, digits, dots, dashes and underscores.</p>
        </div>
        {save.error ? <ErrorAlert error={save.error} title="The config was not saved" /> : null}
        <Button className="self-start" disabled={save.isPending} onClick={() => save.mutate()}>
          <Save /> Save config
        </Button>
      </CardContent>
    </Card>
  );
}

function DeleteConfigButton({ name }: { name: string }) {
  const changed = useConfigsChanged();
  const remove = useMutation({ mutationFn: () => api.deleteModelConfig(name), onSuccess: changed });
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete ${name}`}>
          <Trash2 />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete config {name}?</AlertDialogTitle>
          <AlertDialogDescription>
            New matches can no longer seat it. Matches it played keep their results on the leaderboard.
            {remove.error ? <span className="mt-2 block text-destructive">{remove.error.message}</span> : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={(event) => {
              // keep the dialog open until the delete succeeds or shows its error
              event.preventDefault();
              remove.mutate();
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function SavedConfigs({ configs }: { configs: SavedModelConfig[] }) {
  if (!configs.length) return <p className="p-4 text-sm text-muted-foreground">No saved configs yet.</p>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Model and reasoning</TableHead>
          <TableHead>Other settings</TableHead>
          <TableHead className="w-8" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {configs.map(({ name, config }) => (
          <TableRow key={name}>
            <TableCell className="font-medium">{name}</TableCell>
            <TableCell>
              <span className="inline-flex items-center gap-2">
                <ProviderLogo model={config.model} />
                {configBrief(config)}
              </span>
            </TableCell>
            <TableCell className="whitespace-normal text-muted-foreground">{otherSettings(config)}</TableCell>
            <TableCell>
              <DeleteConfigButton name={name} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ModelsView() {
  const options = useQuery({ queryKey: ["match-options"], queryFn: api.matchOptions, staleTime: Infinity });
  const configs = useQuery({ queryKey: ["model-configs"], queryFn: api.modelConfigs });
  const error = options.error ?? configs.error;
  return (
    <>
      <PageTitle
        title="Models"
        description="A model config is a model with its settings under one name. Matches seat configs, and the leaderboard ranks each config on its own."
      />
      {error ? <ErrorAlert error={error} /> : null}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
        {options.data ? <NewConfigForm options={options.data} /> : options.isPending ? <LoadingRows /> : null}
        <Card className="gap-2 pb-0">
          <CardHeader>
            <CardTitle>Saved configs</CardTitle>
          </CardHeader>
          <CardContent className="px-2">{configs.data ? <SavedConfigs configs={configs.data} /> : configs.isPending ? <LoadingRows /> : null}</CardContent>
        </Card>
      </div>
    </>
  );
}
