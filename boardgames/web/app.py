"""HTTP layer: JSON endpoints over the match store and the static single-page viewer.

Handlers read the store from `request.app.state.store`, so tests build an app
over a temporary directory with `create_app`.
"""

from collections import OrderedDict
from collections.abc import Awaitable, Callable
from importlib.resources import files
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from pydantic import JsonValue as PlainJson

from boardgames.arena.match_config import (
    DEFAULT_MODEL,
    SUGGESTED_MODELS,
    builtin_seat_defaults,
)
from boardgames.core import ArenaError, ConfigError, UnknownGameError, create_game
from boardgames.games import game_ids
from boardgames.logs.replay import ReplayMismatchError
from boardgames.logs.schema import plain_object
from boardgames.web.launcher import (
    Example,
    Launch,
    MatchLauncher,
    UnknownLaunchError,
)
from boardgames.web.layouts import game_layout
from boardgames.web.stats import AgentDetail, Leaderboard, agent_detail, leaderboard
from boardgames.web.store import Catalog, MatchStore, MatchSummary, UnknownMatchError
from boardgames.web.timeline import (
    Frame,
    Outline,
    Timeline,
    build_timeline,
    outline,
    shortened,
)

TIMELINE_CACHE_SIZE = 16
PROBED_PLAYER_COUNTS = range(1, 9)


class UnknownFrameError(ArenaError):
    """A step outside the match's timeline."""


class UnreplayableLogError(ArenaError):
    """A log whose setup no longer replays under the current game rules."""


class UnknownAgentError(ArenaError):
    """No finished match has a seat with this agent name."""


class GameInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    default_config: dict[str, PlainJson]
    matches: int


class GameDetail(GameInfo):
    rules: str


class GameOption(BaseModel):
    """What the new-match form needs per game: its name and goal from the rules,
    seat counts and default settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    summary: str
    player_counts: list[int]
    settings: dict[str, PlainJson]


class MatchOptions(BaseModel):
    """Choices the new-match form offers, and what an untouched seat plays with."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    default_model: str
    models: list[str]
    seat_defaults: dict[str, PlainJson]
    games: list[GameOption]


class StartRequest(BaseModel):
    """A match config as YAML text, as the new-match page sends it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    yaml: str


class TimelineCache:
    """Timelines by match id, rebuilt when the match's step count or status changes."""

    def __init__(self, size: int = TIMELINE_CACHE_SIZE) -> None:
        self._size = size
        self._entries: OrderedDict[str, tuple[tuple[int, str], Timeline]] = (
            OrderedDict()
        )
        return

    def timeline(self, store: MatchStore, summary: MatchSummary) -> Timeline:
        key = (summary.steps, summary.status)
        cached = self._entries.get(summary.match_id)
        if cached is not None and cached[0] == key:
            self._entries.move_to_end(summary.match_id)
            return cached[1]
        timeline = build_timeline(store.records(summary.match_id))
        self._entries[summary.match_id] = (key, timeline)
        while len(self._entries) > self._size:
            self._entries.popitem(last=False)
        return timeline


def store_of(request: Request) -> MatchStore:
    store: MatchStore = request.app.state.store
    return store


def cache_of(request: Request) -> TimelineCache:
    cache: TimelineCache = request.app.state.timelines
    return cache


def launcher_of(request: Request) -> MatchLauncher:
    launcher: MatchLauncher = request.app.state.launcher
    return launcher


def game_option(game_id: str) -> GameOption:
    """A game's valid seat counts, found by asking its config parser, and settings."""
    game = create_game(game_id)
    settings = plain_object(game.config_json(game.parse_config({})))
    settings.pop("num_players", None)
    rules = game.rules_text()
    return GameOption(
        id=game_id,
        name=rules_title(rules) or game_id,
        summary=rules_summary(rules),
        player_counts=[n for n in PROBED_PLAYER_COUNTS if accepts_players(game_id, n)],
        settings=settings,
    )


def rules_title(rules: str) -> str:
    """The text of the rules' first heading, or empty."""
    heading = next((line for line in rules.splitlines() if line.startswith("# ")), "")
    return heading.removeprefix("# ").strip()


def rules_summary(rules: str) -> str:
    """The first sentence of the rules' first paragraph, which states the goal."""
    paragraph = next(
        (
            line.strip()
            for line in rules.splitlines()
            if line.strip() and not line.startswith("#")
        ),
        "",
    )
    end = paragraph.find(". ")
    return paragraph if end < 0 else paragraph[: end + 1]


def accepts_players(game_id: str, count: int) -> bool:
    """Whether the game's config parser accepts `count` players."""
    try:
        create_game(game_id).parse_config({"num_players": count})
    except ConfigError:
        return False
    return True


def game_info(game_id: str, catalog: Catalog) -> GameInfo:
    game = create_game(game_id)
    return GameInfo(
        id=game_id,
        default_config=plain_object(game.config_json(game.parse_config({}))),
        matches=sum(1 for m in catalog.matches if m.game_id == game_id),
    )


api = APIRouter(prefix="/api")


@api.get("/games")
def list_games(request: Request) -> list[GameInfo]:
    catalog = store_of(request).catalog()
    return [game_info(game_id, catalog) for game_id in game_ids()]


@api.get("/match-options")
def match_options() -> MatchOptions:
    """Games with their seat counts and settings, the default model and cheap models."""
    return MatchOptions(
        default_model=DEFAULT_MODEL,
        models=list(SUGGESTED_MODELS),
        seat_defaults=builtin_seat_defaults(),
        games=[game_option(game_id) for game_id in game_ids()],
    )


@api.get("/examples")
def list_examples(request: Request) -> list[Example]:
    """The example match configs the new-match page offers."""
    return launcher_of(request).examples()


@api.post("/matches", status_code=201)
async def start_match(request: Request, body: StartRequest) -> Launch:
    """Start the match a YAML config describes; it runs on the server's loop."""
    return launcher_of(request).start(body.yaml)


@api.get("/launches")
def list_launches(request: Request) -> list[Launch]:
    """Matches started from the viewer, newest first, with failures."""
    return launcher_of(request).launches()


@api.get("/launches/{match_id}")
def launch_status(request: Request, match_id: str) -> Launch:
    """One started match's status; 404 for matches not started from this server."""
    return launcher_of(request).launch(match_id)


@api.post("/launches/{match_id}/pause")
def pause_match(request: Request, match_id: str) -> Launch:
    """Hold the match before its next round."""
    return launcher_of(request).pause(match_id)


@api.post("/launches/{match_id}/resume")
def resume_match(request: Request, match_id: str) -> Launch:
    """Let a paused match play on."""
    return launcher_of(request).resume(match_id)


@api.post("/launches/{match_id}/stop")
async def stop_match(request: Request, match_id: str) -> Launch:
    """End the match now; its log closes with match_stopped."""
    return await launcher_of(request).stop(match_id)


@api.get("/games/{game_id}")
def game_detail(request: Request, game_id: str) -> GameDetail:
    info = game_info(game_id, store_of(request).catalog())
    return GameDetail(**info.model_dump(), rules=create_game(game_id).rules_text())


@api.get("/matches")
def list_matches(
    request: Request, game: str | None = None, agent: str | None = None
) -> Catalog:
    """Matches newest first, filtered by game id and by an agent name at any seat."""
    catalog = store_of(request).catalog()
    matches = [
        m
        for m in catalog.matches
        if (game is None or m.game_id == game)
        and (agent is None or any(seat.agent == agent for seat in m.seats))
    ]
    return Catalog(matches=matches, unreadable=catalog.unreadable)


@api.get("/matches/{match_id}")
def match_summary(request: Request, match_id: str) -> MatchSummary:
    return store_of(request).match(match_id)


def timeline_of(request: Request, match_id: str) -> Timeline:
    """The match's timeline; a log whose setup no longer replays gets a short reason."""
    store = store_of(request)
    summary = store.match(match_id)
    try:
        return cache_of(request).timeline(store, summary)
    except ReplayMismatchError as error:
        raise UnreplayableLogError(
            f"This {summary.game_id} log does not replay under the current rules, "
            f"which changed after it was recorded: {shortened(str(error))}"
        ) from error


@api.get("/matches/{match_id}/timeline")
def match_outline(request: Request, match_id: str) -> Outline:
    """Every move, event and score of the match; boards come one frame at a time."""
    return outline(timeline_of(request, match_id))


@api.get("/matches/{match_id}/frames/{step}")
def match_frame(request: Request, match_id: str, step: int) -> Frame:
    frames = timeline_of(request, match_id).frames
    if not 0 <= step < len(frames):
        raise UnknownFrameError(f"match {match_id!r} has no step {step}")
    return frames[step]


@api.get("/leaderboard")
def leaderboard_route(request: Request, game: str | None = None) -> Leaderboard:
    """Agents ranked by Elo at one game, or by win rate across all games."""
    if game is not None:
        create_game(game)
    return leaderboard(store_of(request).catalog().matches, game)


@api.get("/agents/{agent}")
def agent_route(request: Request, agent: str) -> AgentDetail:
    detail = agent_detail(store_of(request).catalog().matches, agent)
    if not detail.games:
        raise UnknownAgentError(f"no finished match of agent {agent!r}")
    return detail


@api.get("/games/{game_id}/layout")
def game_layout_route(request: Request, game_id: str) -> dict[str, PlainJson]:
    create_game(game_id)
    layout = game_layout(game_id)
    if layout is None:
        raise UnknownGameError(f"game {game_id!r} has no drawn layout")
    return layout


def not_found(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"error": str(error)}, status_code=404)


def unprocessable(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"error": str(error)}, status_code=422)


def static_directory() -> Path:
    return Path(str(files("boardgames.web") / "static"))


def index(request: Request) -> FileResponse:
    return FileResponse(static_directory() / "index.html")


def health() -> dict[str, str]:
    """Liveness check for monitors: the server is up and answering."""
    return {"status": "ok"}


async def revalidate_assets(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Pages and static files carry no-cache, so the browser checks each load and a
    new version shows without a hard reload; unchanged files still answer 304."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def create_app(store: MatchStore, launcher: MatchLauncher) -> FastAPI:
    """The viewer application over `store`; `launcher` starts matches from it."""
    app = FastAPI(
        title="Boardgames", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.store = store
    app.state.launcher = launcher
    app.state.timelines = TimelineCache()
    app.include_router(api)
    app.add_exception_handler(UnknownMatchError, not_found)
    app.add_exception_handler(UnknownFrameError, not_found)
    app.add_exception_handler(UnknownAgentError, not_found)
    app.add_exception_handler(UnknownLaunchError, not_found)
    app.add_exception_handler(UnknownGameError, not_found)
    app.add_exception_handler(ArenaError, unprocessable)
    app.middleware("http")(revalidate_assets)
    app.mount("/static", StaticFiles(directory=static_directory()), name="static")
    app.add_api_route("/", index, include_in_schema=False)
    app.add_api_route("/health", health)
    return app
