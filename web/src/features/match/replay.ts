// The replay as a state machine: which step is on screen, whether it plays, and whose view.
// Pure: the page feeds it outline changes and timer ticks and renders what it holds.

export const SPEEDS = [0.5, 1, 2, 4] as const;
export type Speed = (typeof SPEEDS)[number];
/** Milliseconds between steps while playing at 1×. */
export const STEP_MS = 1200;

export type ReplayState = {
  step: number;
  /** The last step of the timeline as loaded. */
  last: number;
  /** Whether the match is still being played, so the timeline can grow. */
  running: boolean;
  playing: boolean;
  speed: Speed;
  /** The seat whose view is shown; null is the spectator. */
  viewer: number | null;
  /** Show every event, private ones included. */
  omniscient: boolean;
};

export type ReplayAction =
  | { type: "outlineChanged"; last: number; running: boolean }
  | { type: "seek"; step: number }
  | { type: "seekBy"; delta: number }
  | { type: "tick" }
  | { type: "togglePlay" }
  | { type: "setSpeed"; speed: Speed }
  | { type: "setViewer"; viewer: number | null }
  | { type: "setOmniscient"; omniscient: boolean };

/** The state a page opens with; a running match opens on its latest step unless the address names one. */
export function initialReplay(options: { step: number | null; last: number; running: boolean; viewer: number | null; omniscient: boolean }): ReplayState {
  const wanted = options.step ?? (options.running ? options.last : 0);
  return {
    step: Math.min(options.last, Math.max(0, wanted)),
    last: options.last,
    running: options.running,
    playing: false,
    speed: 1,
    viewer: options.viewer,
    omniscient: options.omniscient,
  };
}

// Playback stops at the end of a match that can no longer grow.
function settle(state: ReplayState): ReplayState {
  return state.playing && state.step >= state.last && !state.running ? { ...state, playing: false } : state;
}

function seek(state: ReplayState, step: number): ReplayState {
  return settle({ ...state, step: Math.min(state.last, Math.max(0, step)) });
}

export function replayReducer(state: ReplayState, action: ReplayAction): ReplayState {
  switch (action.type) {
    case "outlineChanged": {
      // a page showing the latest step follows the match as it grows
      const following = state.step === state.last && action.last > state.last;
      const next = { ...state, last: action.last, running: action.running };
      return seek(next, following ? action.last : state.step);
    }
    case "seek":
      return seek(state, action.step);
    case "seekBy":
      return seek(state, state.step + action.delta);
    case "tick":
      return state.step >= state.last ? settle(state) : seek(state, state.step + 1);
    case "togglePlay":
      return { ...state, playing: !state.playing };
    case "setSpeed":
      return { ...state, speed: action.speed };
    case "setViewer":
      return { ...state, viewer: action.viewer };
    case "setOmniscient":
      return { ...state, omniscient: action.omniscient };
  }
}

/** "on" at the latest step of a match that is playing; "off" when paused or scrolled back; null when not running. */
export function liveState(state: ReplayState, launchStatus: string | null): "on" | "off" | null {
  if (!state.running) return null;
  const moving = launchStatus === null || launchStatus === "running";
  return moving && state.step === state.last ? "on" : "off";
}

/** The address of the page for this replay state. */
export function replayQuery(matchId: string, state: ReplayState): string {
  const query = new URLSearchParams({ id: matchId });
  if (state.step) query.set("step", String(state.step));
  if (state.viewer !== null) query.set("viewer", String(state.viewer));
  if (state.omniscient) query.set("all", "1");
  return `?${query}`;
}
