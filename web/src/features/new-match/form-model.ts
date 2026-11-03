// The new-match form as a pure reducer: game, game options, one seat per player, seed.
// The view dispatches actions; `matchConfig` turns the state into the config the server takes.
import type { GameOption, MatchOptions, ModelCapabilities, ReasoningEffort } from "@/lib/api";

/** How each game option reads in the form; unknown options get a label from their key. */
export const GAME_OPTIONS: Record<string, { label: string; hint?: string; min?: number; max?: number }> = {
  "catan.victory_points": { label: "Points to win", hint: "10 is the standard game; 5 or 6 makes a shorter one.", min: 3, max: 20 },
  "catan.max_offers_per_turn": { label: "Trade offers per turn", hint: "0 means no limit.", min: 0, max: 20 },
  "puerto_rico.victory_point_supply": { label: "Victory point chips", hint: "0 uses the standard supply; fewer chips end the game sooner.", min: 0 },
  "puerto_rico.max_rounds": { label: "Round limit", hint: "0 plays to the normal end of the game.", min: 0 },
};

const PROVIDERS: Record<string, string> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  google: "Google",
  "meta-llama": "Meta",
  minimax: "MiniMax",
  mistralai: "Mistral",
  moonshotai: "Moonshot AI",
  nvidia: "NVIDIA",
  openai: "OpenAI",
  qwen: "Qwen",
  xiaomi: "Xiaomi",
  "z-ai": "Z.ai",
};

export const EFFORT_LABELS: Record<ReasoningEffort, string> = {
  minimal: "Minimal",
  low: "Low",
  medium: "Medium",
  high: "High",
  xhigh: "Extra high",
  max: "Max",
};
// offered when OpenRouter's details for a model are missing
const GENERIC_EFFORTS: ReasoningEffort[] = ["low", "medium", "high"];

export type SeatFieldKey =
  | "label"
  | "reasoning"
  | "reasoning_effort"
  | "verbosity"
  | "temperature"
  | "max_tokens"
  | "max_illegal_retries"
  | "fallback"
  | "timeout_seconds"
  | "top_p"
  | "persona";

export type SeatField = {
  key: SeatFieldKey;
  label: string;
  kind: "text" | "toggle" | "effort" | "choice" | "number" | "select" | "textarea";
  hint?: string;
  options?: [string, string][];
  step?: string;
  min?: string;
  max?: string;
  /** Hides a field the seat's model does not accept; `caps` is null while unknown. */
  shows?: (caps: ModelCapabilities | null) => boolean;
};

const accepts = (caps: ModelCapabilities | null, parameter: string) => !caps || caps.parameters.includes(parameter);

/** Per-player settings, in plain words; an empty field keeps the default shown in it. */
export const SEAT_FIELDS: SeatField[] = [
  { key: "label", label: "Name", kind: "text", hint: "Defaults to the model; players on the same model get #1, #2." },
  {
    key: "reasoning",
    label: "Reasoning",
    kind: "toggle",
    hint: "Lets the model think before it moves. Off is faster and cheaper.",
    shows: (caps) => !caps || caps.reasoning !== null,
  },
  {
    key: "reasoning_effort",
    label: "Reasoning effort",
    kind: "effort",
    hint: "How much it thinks; the lowest level is the quickest.",
    shows: (caps) => !caps || (caps.reasoning !== null && caps.reasoning.efforts.length > 0),
  },
  {
    key: "verbosity",
    label: "Answer length (verbosity)",
    kind: "choice",
    options: [
      ["low", "Low"],
      ["medium", "Medium"],
      ["high", "High"],
    ],
    hint: "Low keeps replies short and cheap.",
    shows: (caps) => caps !== null && caps.parameters.includes("verbosity"),
  },
  {
    key: "temperature",
    label: "Randomness (temperature)",
    kind: "number",
    step: "0.1",
    min: "0",
    max: "2",
    hint: "0 is steady and predictable, 1 or more is varied.",
    shows: (caps) => accepts(caps, "temperature"),
  },
  { key: "max_tokens", label: "Longest reply (tokens)", kind: "number", step: "1", min: "1", hint: "Reasoning counts toward it." },
  { key: "max_illegal_retries", label: "Second chances after an illegal move", kind: "number", step: "1", min: "0" },
  {
    key: "fallback",
    label: "If it still can't move",
    kind: "select",
    options: [
      ["random", "Play a random legal move"],
      ["default", "Play the game's default move"],
      ["forfeit", "Forfeit the match"],
    ],
  },
  { key: "timeout_seconds", label: "Time limit per reply (seconds)", kind: "number", step: "1", min: "1" },
  { key: "top_p", label: "Top p", kind: "number", step: "0.05", min: "0", max: "1", hint: "Usually left alone.", shows: (caps) => accepts(caps, "top_p") },
  { key: "persona", label: "Personality and extra instructions", kind: "textarea", hint: "For example: play cautiously and trade often." },
];

export const fieldShows = (field: SeatField, caps: ModelCapabilities | null) => !field.shows || field.shows(caps);

export type SettingValue = string | number | boolean;

export type Seat = {
  /** Stable React key; the index changes when a player is removed. */
  id: number;
  model: string;
  /** Whether the seat types a model id instead of picking a listed one. */
  custom: boolean;
  reasoning: boolean;
  settings: Partial<Record<SeatFieldKey, SettingValue>>;
};

export type FormState = {
  options: MatchOptions;
  /** What each model accepts; grows as typed model ids are looked up. */
  capabilities: Record<string, ModelCapabilities>;
  /** Why a typed model id could not be looked up. */
  unknown: Record<string, string>;
  game: string;
  settings: Record<string, SettingValue>;
  seed: string;
  seats: Seat[];
  nextSeatId: number;
};

export type FormAction =
  | { type: "chooseGame"; game: string }
  | { type: "setGameSetting"; key: string; value: SettingValue | undefined }
  | { type: "addSeat" }
  | { type: "removeSeat"; index: number }
  | { type: "chooseModel"; index: number; model: string | null }
  | { type: "typeModel"; index: number; model: string }
  | { type: "modelLookedUp"; model: string; capabilities: ModelCapabilities | null; error: string | null }
  | { type: "setSeatSetting"; index: number; key: SeatFieldKey; value: SettingValue | undefined }
  | { type: "setReasoning"; index: number; on: boolean }
  | { type: "sameModel"; model: string }
  | { type: "setSeed"; seed: string };

export function modelName(id: string): string {
  const slash = id.indexOf("/");
  if (slash < 0) return id;
  const provider = id.slice(0, slash);
  return `${id.slice(slash + 1)} (${PROVIDERS[provider] ?? provider})`;
}

export function playerRange(counts: number[]): string {
  const low = counts[0];
  const high = counts[counts.length - 1];
  return low === high ? `${low} players` : `${low} to ${high} players`;
}

export function capsOf(state: FormState, seat: Seat): ModelCapabilities | null {
  return state.capabilities[seat.model.trim()] ?? null;
}

export function effortChoices(caps: ModelCapabilities | null): ReasoningEffort[] {
  return caps && caps.reasoning ? caps.reasoning.efforts : GENERIC_EFFORTS;
}

export function currentGame(state: FormState): GameOption {
  const game = state.options.games.find((option) => option.id === state.game);
  if (!game) throw new Error(`unknown game ${state.game}`);
  return game;
}

function withoutKeys<T extends object>(object: T, keys: (keyof T)[]): T {
  const copy = { ...object };
  for (const key of keys) delete copy[key];
  return copy;
}

// Turning reasoning on picks the model's lowest effort; off drops the effort.
function withReasoning(seat: Seat, caps: ModelCapabilities | null, on: boolean): Seat {
  if (!on) return { ...seat, reasoning: false, settings: withoutKeys(seat.settings, ["reasoning_effort"]) };
  const choices = effortChoices(caps);
  const effort = seat.settings.reasoning_effort ?? choices[0];
  return { ...seat, reasoning: true, settings: effort === undefined ? seat.settings : { ...seat.settings, reasoning_effort: effort } };
}

// Conservative settings for a newly chosen model: reasoning off when it can be,
// the lowest effort when it must think, and short answers where verbosity applies.
function withModelDefaults(seat: Seat, caps: ModelCapabilities | null): Seat {
  const hidden = SEAT_FIELDS.filter((field) => !fieldShows(field, caps)).map((field) => field.key);
  const cleared = { ...seat, settings: withoutKeys(seat.settings, [...hidden, "reasoning_effort"]) };
  const reasoned = withReasoning(cleared, caps, Boolean(caps?.reasoning?.is_mandatory));
  if (caps && caps.parameters.includes("verbosity")) return { ...reasoned, settings: { ...reasoned.settings, verbosity: "low" } };
  return reasoned;
}

function newSeat(state: FormState): Seat {
  const seat: Seat = { id: state.nextSeatId, model: state.options.default_model, custom: false, reasoning: false, settings: {} };
  return withModelDefaults(seat, state.capabilities[seat.model] ?? null);
}

function addSeat(state: FormState): FormState {
  return { ...state, seats: [...state.seats, newSeat(state)], nextSeatId: state.nextSeatId + 1 };
}

// Keep the players already set up, within the counts the game allows.
function fitSeats(state: FormState): FormState {
  const counts = currentGame(state).player_counts;
  let fitted = { ...state, seats: state.seats.slice(0, counts[counts.length - 1]) };
  while (fitted.seats.length < counts[0]) fitted = addSeat(fitted);
  return fitted;
}

export function initialFormState(options: MatchOptions): FormState {
  const empty: FormState = {
    options,
    capabilities: { ...options.capabilities },
    unknown: {},
    game: options.games[0].id,
    settings: {},
    seed: "",
    seats: [],
    nextSeatId: 0,
  };
  return fitSeats(empty);
}

function updateSeat(state: FormState, index: number, change: (seat: Seat) => Seat): FormState {
  return { ...state, seats: state.seats.map((seat, at) => (at === index ? change(seat) : seat)) };
}

function chooseModel(state: FormState, index: number, model: string | null): FormState {
  return updateSeat(state, index, (seat) => {
    const chosen = model === null ? { ...seat, custom: true, model: "" } : { ...seat, custom: false, model };
    return withModelDefaults(chosen, state.capabilities[chosen.model] ?? null);
  });
}

// A looked-up model applies its conservative settings to every seat that typed it.
function modelLookedUp(state: FormState, action: Extract<FormAction, { type: "modelLookedUp" }>): FormState {
  const capabilities = action.capabilities ? { ...state.capabilities, [action.model]: action.capabilities } : state.capabilities;
  const unknown = action.error ? { ...state.unknown, [action.model]: action.error } : state.unknown;
  const looked = { ...state, capabilities, unknown };
  return {
    ...looked,
    seats: looked.seats.map((seat) => (seat.model.trim() === action.model ? withModelDefaults(seat, capsOf(looked, seat)) : seat)),
  };
}

export function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case "chooseGame":
      return fitSeats({ ...state, game: action.game, settings: {} });
    case "setGameSetting":
      return {
        ...state,
        settings: action.value === undefined ? withoutKeys(state.settings, [action.key]) : { ...state.settings, [action.key]: action.value },
      };
    case "addSeat":
      return addSeat(state);
    case "removeSeat":
      return { ...state, seats: state.seats.filter((_, at) => at !== action.index) };
    case "chooseModel":
      return chooseModel(state, action.index, action.model);
    case "typeModel":
      return updateSeat(state, action.index, (seat) => ({ ...seat, model: action.model }));
    case "modelLookedUp":
      return modelLookedUp(state, action);
    case "setSeatSetting":
      return updateSeat(state, action.index, (seat) => ({
        ...seat,
        settings: action.value === undefined ? withoutKeys(seat.settings, [action.key]) : { ...seat.settings, [action.key]: action.value },
      }));
    case "setReasoning":
      return updateSeat(state, action.index, (seat) => withReasoning(seat, capsOf(state, seat), action.on));
    case "sameModel":
      return state.seats.reduce((next, _, index) => chooseModel(next, index, action.model), state);
    case "setSeed":
      return { ...state, seed: action.seed };
  }
}

/** The match config sent to the server: only what the user filled in. */
export function matchConfig(state: FormState, seed: number | string) {
  const config = { num_players: state.seats.length, ...state.settings };
  const seats = state.seats.map((seat) => {
    const entry: Record<string, SettingValue> = { model: seat.model.trim() || state.options.default_model, ...seat.settings };
    // reasoning and its effort are separate settings; an effort only goes with reasoning on
    const caps = capsOf(state, seat);
    if (!caps || caps.reasoning) entry.reasoning = seat.reasoning;
    if (!seat.reasoning) delete entry.reasoning_effort;
    return entry;
  });
  return { game: state.game, config, seed, seats };
}

/** One line on what this player sends, so the defaults show without opening the settings. */
export function modelBrief(state: FormState, seat: Seat): string {
  const caps = capsOf(state, seat);
  const id = seat.model.trim();
  if (!caps) {
    if (state.unknown[id]) return `${state.unknown[id]}; every setting is offered.`;
    return state.options.catalog_error ? "Model details are unavailable; every setting is offered." : "";
  }
  const parts: string[] = [];
  if (!caps.reasoning) parts.push("Does not reason");
  else if (!seat.reasoning) parts.push("Reasoning off");
  else {
    const effort = seat.settings.reasoning_effort as ReasoningEffort | undefined;
    const stance = caps.reasoning.is_mandatory ? "Always reasons" : "Reasoning on";
    parts.push(`${stance}${effort ? `, ${EFFORT_LABELS[effort].toLowerCase()} effort` : ""}`);
  }
  if (seat.settings.verbosity) parts.push(`${seat.settings.verbosity} verbosity`);
  return parts.join(" · ");
}

export function summaryText(state: FormState): string {
  const models = [...new Set(state.seats.map((seat) => seat.model.trim() || state.options.default_model))];
  const who = models.length === 1 ? `all playing ${modelName(models[0])}` : `${models.length} different models`;
  return `${currentGame(state).name} with ${state.seats.length} players, ${who}.`;
}

/** What an empty seat field keeps, in words. */
export function defaultText(state: FormState, field: SeatField): string {
  const value = state.options.seat_defaults[field.key];
  if (value === null || value === undefined) return "model's default";
  const option = field.options?.find(([code]) => code === value);
  return option ? option[1] : String(value);
}

export function humanize(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
