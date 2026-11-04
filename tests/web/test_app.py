from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgames.arena import cli
from boardgames.core import ConfigError
from boardgames.games.puerto_rico import PuertoRico, PuertoRicoConfig
from boardgames.games.tic_tac_toe import TicTacToe, TicTacToeConfig
from boardgames.logs.schema import DecisionRecord, EventRecord
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore
from tests.arena.support import random_agents
from tests.web.support import (
    CostlyAgent,
    costly_agents,
    play_records,
    without_finish,
    write_match,
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    write_match(tmp_path, "ttt", seed=1, agents=costly_agents(2))
    launcher = MatchLauncher(tmp_path, None, None)
    return TestClient(create_app(MatchStore(tmp_path), launcher))


def test_agent_pages_open_for_model_ids_with_a_slash(tmp_path: Path) -> None:
    agents = [
        CostlyAgent(agent, f"org/model-{seat}", 0.0)
        for seat, agent in enumerate(random_agents(2))
    ]
    write_match(tmp_path, "slash", agents=agents)
    launcher = MatchLauncher(tmp_path, None, None)
    client = TestClient(create_app(MatchStore(tmp_path), launcher))
    assert client.get("/api/agents/org%2Fmodel-0").json()["agent"] == "org/model-0"
    return


def test_games_matches_and_frames(client: TestClient) -> None:
    games = {g["id"]: g for g in client.get("/api/games").json()}
    assert games["tic_tac_toe"]["matches"] == 1
    assert client.get("/api/games/catan").json()["rules"].startswith("#")
    assert len(client.get("/api/games/catan/layout").json()["hexes"]) == 19
    puerto_rico = client.get("/api/games/puerto_rico/layout").json()
    buildings = {building["name"]: building for building in puerto_rico["buildings"]}
    assert len(buildings) == 23
    assert buildings["small_indigo_plant"]["cost"] == 1
    assert buildings["small_indigo_plant"]["production"] == "indigo"
    assert buildings["city_hall"]["victory_points"] == 4
    assert buildings["city_hall"]["city_spaces"] == 2
    assert len(puerto_rico["goods"]) == 5
    matches = client.get("/api/matches", params={"agent": "model-1"}).json()
    assert [m["match_id"] for m in matches["matches"]] == ["ttt"]
    outline = client.get("/api/matches/ttt/timeline").json()
    assert outline["frame_count"] == len(outline["moves"]) + 1
    assert outline["moves"][0]["latency_seconds"] >= 0
    assert datetime.fromisoformat(outline["log_updated_at"]).tzinfo is not None
    frame = client.get("/api/matches/ttt/frames/1").json()
    assert frame["decision"]["trace"]["reasoning"].startswith("I pick")
    board = client.get("/api/leaderboard", params={"game": "tic_tac_toe"}).json()
    assert [row["agent"] for row in board["rows"]][:1] in (["model-0"], ["model-1"])
    assert client.get("/api/agents/model-0").json()["games"][0]["matches"] == 1
    assert client.get("/api/agents/nobody").status_code == 404
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/ttt/frames/99").status_code == 404
    assert client.get("/api/matches/ttt").json()["seats"][0]["model"] == "model-0"
    return


def test_serves_the_viewer_build_with_its_cache_headers(tmp_path: Path) -> None:
    viewer = tmp_path / "out"
    (viewer / "matches").mkdir(parents=True)
    (viewer / "_next" / "static").mkdir(parents=True)
    (viewer / "index.html").write_text("<title>Boardgames</title>")
    (viewer / "matches" / "index.html").write_text("matches page")
    (viewer / "_next" / "static" / "app.js").write_text("")
    (viewer / "city.png").write_bytes(b"")
    launcher = MatchLauncher(tmp_path, None, None)
    app = create_app(MatchStore(tmp_path), launcher, viewer_dir=viewer)
    client = TestClient(app)
    page = client.get("/matches")
    assert page.text == "matches page"
    assert page.headers["cache-control"] == "no-cache"
    bundle = client.get("/_next/static/app.js").headers["cache-control"]
    assert bundle.endswith("immutable")
    assert client.get("/city.png").headers["cache-control"].startswith("max-age=")
    assert "cache-control" not in client.get("/api/games").headers
    return


def test_serve_command_parses_its_options() -> None:
    args = cli.parse_arguments(["serve", "--runs", "logs", "--port", "9000"])
    assert (args.runs, args.port, args.handler) == (Path("logs"), 9000, cli.serve)
    assert args.viewer == Path("web/out")
    assert cli.parse_arguments(["serve"]).port == 8765
    return


def test_serve_command_needs_a_viewer_build(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="pnpm --dir web build"):
        cli.viewer_build(tmp_path / "out")
    return


def test_a_read_only_log_that_vanishes_does_not_break_the_listing(
    tmp_path: Path,
) -> None:
    examples = tmp_path / "examples"
    runs = tmp_path / "runs"
    examples.mkdir()
    runs.mkdir()
    write_match(examples, "example")
    write_match(runs, "kept")
    opened = examples / "example.jsonl"
    client = TestClient(
        create_app(
            MatchStore(runs, read_only=(opened,)),
            MatchLauncher(runs, None, None),
        )
    )
    assert client.get("/api/matches").status_code == 200
    opened.unlink()
    for path in ("/api/matches", "/api/leaderboard", "/api/games"):
        assert client.get(path).status_code == 200
    assert client.get("/api/matches/kept").status_code == 200
    return


def test_a_live_timeline_notices_events_added_to_the_last_step(
    tmp_path: Path,
) -> None:
    records = without_finish(
        play_records(TicTacToe(), TicTacToeConfig(), random_agents(2), 3, "live")
    )
    cut = next(
        i
        for i, record in enumerate(records)
        if isinstance(record, DecisionRecord) and record.step == 3
    )
    events = [
        record
        for record in records[cut + 1 :]
        if isinstance(record, EventRecord) and record.step == 3
    ]
    assert events
    path = tmp_path / "live.jsonl"
    path.write_text(
        "".join(record.model_dump_json() + "\n" for record in records[: cut + 1]),
        encoding="utf-8",
    )
    client = TestClient(
        create_app(MatchStore(tmp_path), MatchLauncher(tmp_path, None, None))
    )
    before = client.get("/api/matches/live/timeline").json()["frame_count"]
    with path.open("a", encoding="utf-8") as log:
        for event in events:
            log.write(event.model_dump_json() + "\n")
    after = client.get("/api/matches/live/timeline").json()["frame_count"]
    assert after == before + 1
    assert client.get("/api/matches/live/frames/3").status_code == 200
    return


def test_puerto_rico_frames_expose_the_board_data(tmp_path: Path) -> None:
    write_match(
        tmp_path,
        "pr",
        seed=2,
        game=PuertoRico(),
        config=PuertoRicoConfig(num_players=3, max_rounds=2),
    )
    launcher = MatchLauncher(tmp_path, None, None)
    client = TestClient(create_app(MatchStore(tmp_path), launcher))
    timeline = client.get("/api/matches/pr/timeline").json()
    assert timeline["frame_count"] > 2
    frame = client.get("/api/matches/pr/frames/2").json()
    board = next(board for board in frame["boards"] if board["viewer"] is None)
    observation = board["observation"]
    assert observation["roles"]
    assert observation["players"]
    assert "public_points" in observation["players"][0]
    assert "building_points" in observation["players"][0]
    assert observation["cargo_ships"]
    assert observation["face_up"] is not None
    assert "phase" in observation
    return
