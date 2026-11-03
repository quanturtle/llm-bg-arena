"""HTTP layer: JSON endpoints over the match store and the static single-page viewer.

Handlers read the store from `request.app.state.store`, so tests build an app
over a temporary directory with `create_app`.
"""

from collections import OrderedDict
from importlib.resources import files
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from pydantic import JsonValue as PlainJson

import boardgames.games  # noqa: F401  (importing registers every game)
from boardgames.core import (
    ArenaError,
    UnknownGameError,
    create_game,
    registered_game_ids,
)
from boardgames.logs.schema import plain_object
from boardgames.web.layouts import game_layout
from boardgames.web.stats import AgentDetail, Leaderboard, agent_detail, leaderboard
from boardgames.web.store import Catalog, MatchStore, MatchSummary, UnknownMatchError
from boardgames.web.timeline import Frame, Outline, Timeline, build_timeline, outline

TIMELINE_CACHE_SIZE = 16


class UnknownFrameError(ArenaError):
    """A step outside the match's timeline."""


class UnknownAgentError(ArenaError):
    """No finished match has a seat with this agent name."""


class GameInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    default_config: dict[str, PlainJson]
    matches: int


class GameDetail(GameInfo):
    rules: str


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
    return [game_info(game_id, catalog) for game_id in registered_game_ids()]


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
    store = store_of(request)
    return cache_of(request).timeline(store, store.match(match_id))


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


def create_app(store: MatchStore) -> FastAPI:
    """The viewer application over `store`."""
    app = FastAPI(
        title="Boardgames", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.store = store
    app.state.timelines = TimelineCache()
    app.include_router(api)
    app.add_exception_handler(UnknownMatchError, not_found)
    app.add_exception_handler(UnknownFrameError, not_found)
    app.add_exception_handler(UnknownAgentError, not_found)
    app.add_exception_handler(UnknownGameError, not_found)
    app.add_exception_handler(ArenaError, unprocessable)
    app.mount("/static", StaticFiles(directory=static_directory()), name="static")
    app.add_api_route("/", index, include_in_schema=False)
    return app
