"use client";

import { useEffect, useReducer } from "react";

import { initialReplay, replayQuery, replayReducer, STEP_MS, type ReplayAction } from "@/features/match/replay";
import type { Outline } from "@/lib/api";

// Keys typed into these go to the control, not to the replay.
const TYPING_TARGETS =
  "input, textarea, select, [role=slider], [role=combobox], [role=listbox], [role=tablist], [contenteditable=true]";

function keyAction(event: KeyboardEvent): ReplayAction | null {
  if (event.key === "ArrowLeft") return { type: "seekBy", delta: -1 };
  if (event.key === "ArrowRight") return { type: "seekBy", delta: 1 };
  if (event.key === "Home") return { type: "seek", step: 0 };
  if (event.key === "End") return { type: "seek", step: Number.POSITIVE_INFINITY };
  if (event.key === " ") return { type: "togglePlay" };
  return null;
}

/** The replay's state, wired to the outline, the play timer, the keyboard and the address bar. */
export function useReplay(matchId: string, outline: Outline, opening: { step: number | null; viewer: number | null; omniscient: boolean }) {
  const last = outline.frame_count - 1;
  const running = outline.match.status === "running";
  const [state, dispatch] = useReducer(replayReducer, { ...opening, last, running }, initialReplay);

  useEffect(() => {
    dispatch({ type: "outlineChanged", last, running });
  }, [last, running]);

  useEffect(() => {
    if (!state.playing) return;
    const timer = setInterval(() => dispatch({ type: "tick" }), STEP_MS / state.speed);
    return () => clearInterval(timer);
  }, [state.playing, state.speed]);

  useEffect(() => {
    window.history.replaceState(null, "", replayQuery(matchId, state));
  }, [matchId, state]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof Element && event.target.closest(TYPING_TARGETS)) return;
      const action = keyAction(event);
      if (!action) return;
      // Space would also press a focused button
      event.preventDefault();
      dispatch(action);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return [state, dispatch] as const;
}
