from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgames.arena import cli
from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.web.app import create_app
from boardgames.web.store import MatchStore
from tests.arena.support import random_agents
from tests.web.support import costly_agents, without_finish, write_match, write_records


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    write_match(tmp_path, "ttt", seed=1, agents=costly_agents(2))
    write_match(
        tmp_path,
        "auction",
        seed=2,
        agents=random_agents(3),
        game=SealedAuction(),
        config=SealedAuctionConfig(num_players=3, lots=2),
    )
    (tmp_path / "broken.jsonl").write_text("{}\n", encoding="utf-8")
    return TestClient(create_app(MatchStore(tmp_path)))


def test_games_list_defaults_and_match_counts(client: TestClient) -> None:
    games = client.get("/api/games").json()
    by_id = {game["id"]: game for game in games}
    assert set(by_id) >= {"k_in_a_row", "sealed_auction", "catan"}
    assert by_id["k_in_a_row"]["matches"] == 1
    assert by_id["k_in_a_row"]["default_config"]["rows"] == 3
    detail = client.get("/api/games/sealed_auction").json()
    assert detail["rules"].startswith("#")
    assert client.get("/api/games/chess").status_code == 404
    return


def test_matches_are_listed_and_filtered(client: TestClient) -> None:
    catalog = client.get("/api/matches").json()
    assert {m["match_id"] for m in catalog["matches"]} == {"ttt", "auction"}
    assert [u["path"] for u in catalog["unreadable"]] == ["broken.jsonl"]
    by_game = client.get("/api/matches", params={"game": "k_in_a_row"}).json()
    assert [m["match_id"] for m in by_game["matches"]] == ["ttt"]
    by_agent = client.get("/api/matches", params={"agent": "model-1"}).json()
    assert [m["match_id"] for m in by_agent["matches"]] == ["ttt"]
    none = client.get("/api/matches", params={"agent": "nobody"}).json()
    assert none["matches"] == []
    return


def test_match_summary_and_timeline(client: TestClient) -> None:
    summary = client.get("/api/matches/ttt").json()
    assert summary["seats"][0]["agent"] == "model-0"
    outline = client.get("/api/matches/ttt/timeline").json()
    assert outline["match"]["match_id"] == "ttt"
    assert outline["frame_count"] == summary["steps"] + 1
    assert len(outline["moves"]) == summary["steps"]
    assert outline["moves"][0]["step"] == 1
    assert outline["moves"][0]["illegal_attempts"] == 1
    assert len(outline["scores"]) == outline["frame_count"]
    assert outline["events"][0]["kind"] == "started"
    frame = client.get("/api/matches/ttt/frames/1").json()
    assert frame["decision"]["trace"]["reasoning"].startswith("I pick")
    assert frame["boards"][0]["viewer"] is None
    assert client.get("/api/matches/ttt/frames/999").status_code == 404
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/nope/timeline").status_code == 404
    return


def test_layouts_exist_only_for_drawn_boards(client: TestClient) -> None:
    layout = client.get("/api/games/catan/layout").json()
    assert len(layout["hexes"]) == 19
    assert len(layout["vertices"]) == 54
    assert len(layout["edges"]) == 72
    assert client.get("/api/games/k_in_a_row/layout").status_code == 404
    assert client.get("/api/games/chess/layout").status_code == 404
    return


def test_timeline_is_rebuilt_when_a_running_match_advances(tmp_path: Path) -> None:
    records = write_match(tmp_path, "live")
    path = tmp_path / "live.jsonl"
    path.unlink()
    third_decision = next(
        i for i, r in enumerate(records) if r.type == "decision" and r.step == 3
    )
    write_records(path, without_finish(records[:third_decision]))
    client = TestClient(create_app(MatchStore(tmp_path)))
    first = client.get("/api/matches/live/timeline").json()
    assert first["match"]["status"] == "running"
    path.unlink()
    write_records(path, records)
    second = client.get("/api/matches/live/timeline").json()
    assert second["match"]["status"] == "finished"
    assert second["frame_count"] > first["frame_count"]
    return


def test_a_log_that_does_not_replay_is_unprocessable(tmp_path: Path) -> None:
    records = write_match(tmp_path, "bad")
    path = tmp_path / "bad.jsonl"
    path.unlink()
    decisions = [i for i, r in enumerate(records) if r.type == "decision"]
    first, second = records[decisions[0]], records[decisions[1]]
    assert first.type == "decision" and second.type == "decision"
    tampered = list(records)
    tampered[decisions[1]] = second.model_copy(update={"action": first.action})
    write_records(path, tampered)
    client = TestClient(create_app(MatchStore(tmp_path)))
    response = client.get("/api/matches/bad/timeline")
    assert response.status_code == 422
    assert response.json()["error"].startswith("step 2:")
    return


def test_index_serves_the_viewer_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>Boardgames</title>" in response.text
    return


def test_serve_command_parses_its_options() -> None:
    args = cli.parse_arguments(["serve", "--runs", "logs", "--port", "9000"])
    assert (args.runs, args.host, args.port) == (Path("logs"), "127.0.0.1", 9000)
    assert args.handler is cli.serve
    return
