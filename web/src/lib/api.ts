// The viewer's one I/O seam: typed calls to the FastAPI app in boardgames/web/app.py.
import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];
export type AgentDetail = Schemas["AgentDetail"];
export type AgentGameStats = Schemas["AgentGameStats"];
export type BoardView = Schemas["BoardView"];
export type Catalog = Schemas["Catalog"];
export type DecisionView = Schemas["DecisionView"];
export type EventRecord = Schemas["EventRecord"];
export type Example = Schemas["Example"];
export type ForfeitView = Schemas["ForfeitView"];
export type Frame = Schemas["Frame"];
export type GameDetail = Schemas["GameDetail"];
export type GameInfo = Schemas["GameInfo"];
export type GameOption = Schemas["GameOption"];
export type HeadToHead = Schemas["HeadToHead"];
export type Launch = Schemas["Launch"];
export type LaunchStatus = Schemas["LaunchStatus"];
export type Leaderboard = Schemas["Leaderboard"];
export type MatchOptions = Schemas["MatchOptions"];
export type MatchSummary = Schemas["AnyMatch"];
export type MatchStatus = MatchSummary["status"];
export type ModelCapabilities = Schemas["ModelCapabilities"];
export type Outline = Schemas["Outline"];
export type ReasoningEffort = Schemas["ReasoningEffort"];
export type ScoreView = Schemas["ScoreView"];
export type SeatSummary = MatchSummary["seats"][number];
export type TraceRecord = Schemas["TraceRecord"];
export type JsonObject = { [key: string]: unknown };
export type LaunchAction = "pause" | "resume" | "stop";

/** A failed request, carrying the server's `{"error": ...}` text when it sent one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isErrorBody(body: unknown): body is { error: string } {
  return typeof body === "object" && body !== null && typeof (body as { error?: unknown }).error === "string";
}

async function errorText(response: Response): Promise<string> {
  const fallback = `${response.status} ${response.statusText}`;
  // a body that is not JSON keeps the status text
  const body: unknown = await response.json().catch(() => null);
  return isErrorBody(body) ? body.error : fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw new ApiError(response.status, await errorText(response));
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  if (body === undefined) return request<T>(path, { method: "POST" });
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** `?key=value` for the non-empty values, or an empty string. */
function search(params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
  const text = query.toString();
  return text ? `?${text}` : "";
}

const segment = encodeURIComponent;

async function orNullWhenMissing<T>(pending: Promise<T>): Promise<T | null> {
  try {
    return await pending;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** One started match's status; null for a match this server did not start. */
function launchOrNull(matchId: string): Promise<Launch | null> {
  return orNullWhenMissing(request<Launch>(`/api/launches/${segment(matchId)}`));
}

/** The static geometry of a drawn board; null for a game drawn from its observation alone. */
function layoutOrNull(gameId: string): Promise<JsonObject | null> {
  return orNullWhenMissing(request<JsonObject>(`/api/games/${segment(gameId)}/layout`));
}

export const api = {
  games: () => request<GameInfo[]>("/api/games"),
  game: (gameId: string) => request<GameDetail>(`/api/games/${segment(gameId)}`),
  layout: layoutOrNull,
  matches: (filters: { game?: string; agent?: string }) => request<Catalog>(`/api/matches${search(filters)}`),
  timeline: (matchId: string) => request<Outline>(`/api/matches/${segment(matchId)}/timeline`),
  frame: (matchId: string, step: number) => request<Frame>(`/api/matches/${segment(matchId)}/frames/${step}`),
  deleteMatch: (matchId: string) => request<null>(`/api/matches/${segment(matchId)}`, { method: "DELETE" }),
  leaderboard: (filters: { game?: string; prompt?: string }) => request<Leaderboard>(`/api/leaderboard${search(filters)}`),
  agent: (name: string) => request<AgentDetail>(`/api/agents/${segment(name)}`),
  launches: () => request<Launch[]>("/api/launches"),
  launch: launchOrNull,
  controlLaunch: (matchId: string, action: LaunchAction) => post<Launch>(`/api/launches/${segment(matchId)}/${action}`),
  matchOptions: () => request<MatchOptions>("/api/match-options"),
  modelCapabilities: (model: string) => request<ModelCapabilities>(`/api/model-capabilities${search({ model })}`),
  examples: () => request<Example[]>("/api/examples"),
  startMatch: (yaml: string) => post<Launch>("/api/matches", { yaml }),
};
