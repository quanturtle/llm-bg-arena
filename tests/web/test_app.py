from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgames.arena import cli
from boardgames.games.puerto_rico import PuertoRico, PuertoRicoConfig
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore
from tests.arena.support import random_agents
from tests.web.support import CostlyAgent, costly_agents, write_match


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
    assert len(puerto_rico["goods"]) == 5
    assert "window.boards.puerto_rico" in client.get("/static/puerto_rico.js").text
    assert ".puerto-rico" in client.get("/static/puerto_rico.css").text
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
    assert "<title>Boardgames</title>" in client.get("/").text
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/games").headers
    assert client.get("/api/matches/ttt").json()["seats"][0]["model"] == "model-0"
    return


def test_serve_command_parses_its_options() -> None:
    args = cli.parse_arguments(["serve", "--runs", "logs", "--port", "9000"])
    assert (args.runs, args.port, args.handler) == (Path("logs"), 9000, cli.serve)
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
    assert observation["public_points"]
    assert observation["cargo_ships"]
    assert observation["face_up"] is not None
    assert "phase" in observation
    return
