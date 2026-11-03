"use client";

import { ChevronDown, X } from "lucide-react";

import { SeatDot } from "@/components/seat";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  capsOf,
  currentGame,
  defaultText,
  EFFORT_LABELS,
  effortChoices,
  fieldShows,
  modelBrief,
  SEAT_FIELDS,
  type FormAction,
  type FormState,
  type Seat,
  type SeatField,
} from "@/features/new-match/form-model";
import { ModelPicker } from "@/features/new-match/model-picker";
import type { ModelCapabilities, ReasoningEffort } from "@/lib/api";

// Radix selects take no empty value, so this stands for "keep the default".
const KEEP_DEFAULT = "__default";

type FieldProps = {
  state: FormState;
  field: SeatField;
  seat: Seat;
  index: number;
  caps: ModelCapabilities | null;
  dispatch: React.Dispatch<FormAction>;
};

function SeatInput({ state, field, seat, index, caps, dispatch }: FieldProps) {
  const current = seat.settings[field.key];
  const set = (value: string | number | undefined) => dispatch({ type: "setSeatSetting", index, key: field.key, value });
  if (field.kind === "toggle") {
    const mandatory = Boolean(caps?.reasoning?.is_mandatory);
    return (
      <div className="flex h-8 items-center gap-2 text-sm">
        <Switch checked={seat.reasoning} disabled={mandatory} onCheckedChange={(on) => dispatch({ type: "setReasoning", index, on })} />
        {mandatory ? "On: this model always reasons" : seat.reasoning ? "On" : "Off"}
      </div>
    );
  }
  if (field.kind === "effort") {
    const modelDefault = caps?.reasoning?.default_effort ?? null;
    return (
      <Select value={seat.reasoning ? String(current ?? "") : ""} disabled={!seat.reasoning} onValueChange={set}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Reasoning is off" />
        </SelectTrigger>
        <SelectContent>
          {effortChoices(caps).map((level: ReasoningEffort) => (
            <SelectItem key={level} value={level}>
              {EFFORT_LABELS[level] ?? level}
              {level === modelDefault ? " · model's default" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (field.kind === "choice" || field.kind === "select") {
    const keepsDefault = field.kind === "select";
    const options = (field.options ?? []).filter(([code]) => !keepsDefault || code !== state.options.seat_defaults[field.key]);
    const text = defaultText(state, field);
    return (
      <Select
        value={current === undefined ? (keepsDefault ? KEEP_DEFAULT : "") : String(current)}
        onValueChange={(value) => set(value === KEEP_DEFAULT ? undefined : value)}
      >
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {keepsDefault ? <SelectItem value={KEEP_DEFAULT}>{text === "model's default" ? text : `${text} (default)`}</SelectItem> : null}
          {options.map(([code, label]) => (
            <SelectItem key={code} value={code}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  if (field.kind === "textarea") {
    return (
      <Textarea
        rows={2}
        placeholder={field.hint ?? ""}
        value={current === undefined ? "" : String(current)}
        onChange={(event) => set(event.target.value === "" ? undefined : event.target.value)}
      />
    );
  }
  const modelTemperature = field.key === "temperature" && caps?.default_temperature != null ? String(caps.default_temperature) : null;
  const fallback = modelTemperature ?? defaultText(state, field);
  const placeholder = field.key === "label" ? "the model's name" : fallback.startsWith("model") ? fallback : `default: ${fallback}`;
  const max = field.key === "max_tokens" && caps?.max_output_tokens ? String(caps.max_output_tokens) : field.max;
  const numeric = field.kind === "number";
  return (
    <Input
      type={numeric ? "number" : "text"}
      step={field.step}
      min={field.min}
      max={max}
      placeholder={placeholder}
      value={current === undefined ? "" : String(current)}
      onChange={(event) => {
        const raw = event.target.value;
        set(raw === "" ? undefined : numeric ? Number(raw) : raw);
      }}
    />
  );
}

/** One player: its model, a line on what it sends, and the model's settings folded away. */
export function SeatCard({
  state,
  seat,
  index,
  dispatch,
  onTyped,
}: {
  state: FormState;
  seat: Seat;
  index: number;
  dispatch: React.Dispatch<FormAction>;
  onTyped: (model: string) => void;
}) {
  const caps = capsOf(state, seat);
  const removable = state.seats.length > currentGame(state).player_counts[0];
  const brief = modelBrief(state, seat);
  return (
    <Card className="gap-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SeatDot player={index} className="size-2.5" />
          Player {index + 1}
        </CardTitle>
        {removable ? (
          <CardAction>
            <Button variant="ghost" size="icon-sm" aria-label="Remove this player" onClick={() => dispatch({ type: "removeSeat", index })}>
              <X />
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Model</Label>
          <ModelPicker
            models={state.options.models}
            defaultModel={state.options.default_model}
            model={seat.model}
            custom={seat.custom}
            onChoose={(model) => dispatch({ type: "chooseModel", index, model })}
            onType={(model) => dispatch({ type: "typeModel", index, model })}
            onTyped={() => onTyped(seat.model.trim())}
          />
          {brief ? <p className="text-xs text-muted-foreground">{brief}</p> : null}
        </div>
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="group -ml-2 text-muted-foreground">
              <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" />
              Model settings
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 flex flex-col gap-3">
            {SEAT_FIELDS.filter((field) => fieldShows(field, caps)).map((field) => (
              <div key={field.key} className="flex flex-col gap-1.5" title={field.hint ?? ""}>
                <Label className="text-muted-foreground">{field.label}</Label>
                <SeatInput state={state} field={field} seat={seat} index={index} caps={caps} dispatch={dispatch} />
                {field.hint && field.kind !== "textarea" ? <p className="text-xs text-muted-foreground">{field.hint}</p> : null}
              </div>
            ))}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
