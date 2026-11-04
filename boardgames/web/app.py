"""HTTP layer: JSON endpoints over the match store, and the built Next.js viewer.

Handlers read the store from `request.app.state.store`, so tests build an app
over a temporary directory with `create_app`.
"""

from collections import OrderedDict
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
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
from boardgames.llm.catalog import (
    CatalogUnavailableError,
    ModelCapabilities,
    ModelCatalog,
)
from boardgames.logs.replay import ReplayMismatchError
from boardgames.logs.schema import plain_object
from boardgames.web.launcher import (
    Example,
    Launch,
    MatchLauncher,
    MatchStillPlayingError,
    UnknownLaunchError,
)
from boardgames.web.layouts import game_layout
from boardgames.web.stats import AgentDetail, Leaderboard, agent_detail, leaderboard
from boardgames.web.store import (
    Catalog,
    MatchStore,
    MatchSummary,
    ReadOnlyLogError,
    UnknownMatchError,
)
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
IMAGE_MAX_AGE_SECONDS = 86400
BUNDLE_PREFIX = "/_next/static/"
BUNDLE_CACHE_CONTROL = "max-age=31536000, immutable"


class UnknownFrameError(ArenaError):
    """A step outside the match's timeline."""


class UnreplayableLogError(ArenaError):
    """A log whose setup no longer replays under the current game rules."""


class UnknownAgentError(ArenaError):
    """No finished match has a seat with this agent name."""


class UnknownModelError(ArenaError):
    """OpenRouter's model list has no model with this id."""


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
    """Choices the new-match form offers, and what an untouched seat plays with.

    `capabilities` has what each suggested model accepts; it is empty, with the
    reason in `catalog_error`, when OpenRouter's model list could not be read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    default_model: str
    models: list[str]
    capabilities: dict[str, ModelCapabilities]
    catalog_error: str | None
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
        self._entries: OrderedDict[
            str, tuple[tuple[int, str, tuple[int, int]], Timeline]
        ] = OrderedDict()
        return

    def timeline(self, store: MatchStore, summary: MatchSummary) -> Timeline:
        key = (summary.steps, summary.status, store.stamp(summary.match_id))
        cached = self._entries.get(summary.match_id)
        if cached is not None and cached[0] == key:
            self._entries.move_to_end(summary.match_id)
            return cached[1]
        timeline = build_timeline(store.records(summary.match_id))
        self._entries[summary.match_id] = (key, timeline)
        while len(self._entries) > self._size:
            self._entries.popitem(last=False)
        return timeline

    def forget(self, match_id: str) -> None:
        """Drop a deleted match's timeline."""
        self._entries.pop(match_id, None)
        return


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
async def match_options(request: Request) -> MatchOptions:
    """Games with seat counts and settings, and cheap models with what they take."""
    capabilities, catalog_error = await suggested_capabilities(catalog_of(request))
    return MatchOptions(
        default_model=DEFAULT_MODEL,
        models=list(SUGGESTED_MODELS),
        capabilities=capabilities,
        catalog_error=catalog_error,
        seat_defaults=builtin_seat_defaults(),
        games=[game_option(game_id) for game_id in game_ids()],
    )


def catalog_of(request: Request) -> ModelCatalog | None:
    catalog: ModelCatalog | None = request.app.state.catalog
    return catalog


async def suggested_capabilities(
    catalog: ModelCatalog | None,
) -> tuple[dict[str, ModelCapabilities], str | None]:
    """What each suggested model accepts, or why that is unknown."""
    if catalog is None:
        return {}, None
    try:
        found = {model: await catalog.lookup(model) for model in SUGGESTED_MODELS}
    except CatalogUnavailableError as error:
        return {}, str(error)
    return {model: info for model, info in found.items() if info is not None}, None


@api.get("/model-capabilities")
async def model_capabilities(request: Request, model: str) -> ModelCapabilities:
    """What one OpenRouter model accepts; 404 for ids OpenRouter does not list."""
    catalog = catalog_of(request)
    if catalog is None:
        raise CatalogUnavailableError("this server does not read OpenRouter's models")
    found = await catalog.lookup(model)
    if found is None:
        raise UnknownModelError(f"OpenRouter lists no model {model!r}")
    return found


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
async def pause_match(request: Request, match_id: str) -> Launch:
    """Hold the match before its next round; runs on the loop that owns the gate."""
    return launcher_of(request).pause(match_id)


@api.post("/launches/{match_id}/resume")
async def resume_match(request: Request, match_id: str) -> Launch:
    """Let a paused match play on; runs on the loop that owns the gate."""
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


@api.delete("/matches/{match_id}", status_code=204)
async def delete_match(request: Request, match_id: str) -> Response:
    """Delete a match's log and thoughts file; a match still playing here is 409."""
    launcher = launcher_of(request)
    launcher.check_forgettable(match_id)
    store_of(request).delete(match_id)
    cache_of(request).forget(match_id)
    launcher.forget(match_id)
    return Response(status_code=204)


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
    timeline = timeline_of(request, match_id)
    return outline(timeline, store_of(request).updated_at(match_id))


@api.get("/matches/{match_id}/frames/{step}")
def match_frame(request: Request, match_id: str, step: int) -> Frame:
    frames = timeline_of(request, match_id).frames
    if not 0 <= step < len(frames):
        raise UnknownFrameError(f"match {match_id!r} has no step {step}")
    return frames[step]


@api.get("/leaderboard")
def leaderboard_route(
    request: Request, game: str | None = None, prompt: int | None = None
) -> Leaderboard:
    """Agents ranked by Elo at one game, or by win rate across all games.

    `prompt` keeps only matches played with that prompt version; 0 means unversioned."""
    if game is not None:
        create_game(game)
    return leaderboard(store_of(request).catalog().matches, game, prompt)


# `:path` lets an agent name that is a model id ("openai/gpt-5-nano") keep its slash
@api.get("/agents/{agent:path}")
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


def conflict(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"error": str(error)}, status_code=409)


def unavailable(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"error": str(error)}, status_code=503)


def health() -> dict[str, str]:
    """Liveness check for monitors: the server is up and answering."""
    return {"status": "ok"}


async def revalidate_assets(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Pages carry no-cache, so a new viewer build shows without a hard reload.
    Next's bundles have hashed names and never change; images keep for a day."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith(BUNDLE_PREFIX):
        response.headers["Cache-Control"] = BUNDLE_CACHE_CONTROL
    elif path.endswith(".png"):
        response.headers["Cache-Control"] = f"max-age={IMAGE_MAX_AGE_SECONDS}"
    elif not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def create_app(
    store: MatchStore,
    launcher: MatchLauncher,
    catalog: ModelCatalog | None = None,
    viewer_dir: Path | None = None,
) -> FastAPI:
    """The viewer application over `store`; `launcher` starts matches from it.

    `catalog` tells the new-match form what each model accepts; None shows them all.
    `viewer_dir` is the built Next.js viewer (web/out); None serves the API alone.
    """
    app = FastAPI(
        title="Boardgames", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.store = store
    app.state.launcher = launcher
    app.state.catalog = catalog
    app.state.timelines = TimelineCache()
    app.include_router(api)
    app.add_exception_handler(UnknownMatchError, not_found)
    app.add_exception_handler(UnknownFrameError, not_found)
    app.add_exception_handler(UnknownAgentError, not_found)
    app.add_exception_handler(UnknownLaunchError, not_found)
    app.add_exception_handler(UnknownGameError, not_found)
    app.add_exception_handler(UnknownModelError, not_found)
    app.add_exception_handler(MatchStillPlayingError, conflict)
    app.add_exception_handler(ReadOnlyLogError, conflict)
    app.add_exception_handler(CatalogUnavailableError, unavailable)
    app.add_exception_handler(ArenaError, unprocessable)
    app.middleware("http")(revalidate_assets)
    app.add_api_route("/health", health)
    # mounted last, so every API route above wins; /matches redirects to /matches/
    if viewer_dir is not None:
        app.mount("/", StaticFiles(directory=viewer_dir, html=True), name="viewer")
    return app
