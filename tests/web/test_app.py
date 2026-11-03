from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgames.arena import cli
from boardgames.web.app import create_app
from boardgames.web.store import MatchStore
from tests.web.support import costly_agents, write_match


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    write_match(tmp_path, "ttt", seed=1, agents=costly_agents(2))
    return TestClient(create_app(MatchStore(tmp_path)))


def test_games_matches_and_frames(client: TestClient) -> None:
    games = {g["id"]: g for g in client.get("/api/games").json()}
    assert games["k_in_a_row"]["matches"] == 1
    assert client.get("/api/games/catan").json()["rules"].startswith("#")
    assert len(client.get("/api/games/catan/layout").json()["hexes"]) == 19
    matches = client.get("/api/matches", params={"agent": "model-1"}).json()
    assert [m["match_id"] for m in matches["matches"]] == ["ttt"]
    outline = client.get("/api/matches/ttt/timeline").json()
    assert outline["frame_count"] == len(outline["moves"]) + 1
    frame = client.get("/api/matches/ttt/frames/1").json()
    assert frame["decision"]["trace"]["reasoning"].startswith("I pick")
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/ttt/frames/99").status_code == 404
    assert "<title>Boardgames</title>" in client.get("/").text
    return


def test_serve_command_parses_its_options() -> None:
    args = cli.parse_arguments(["serve", "--runs", "logs", "--port", "9000"])
    assert (args.runs, args.port, args.handler) == (Path("logs"), 9000, cli.serve)
    return
