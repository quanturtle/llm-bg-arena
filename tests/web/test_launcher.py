import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgames.core import ConfigError
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore

BOT_MATCH = "game: k_in_a_row\nseats: [{agent: random}, {agent: random}]\n"


def test_launcher_starts_a_match_and_reports_how_it_ended(tmp_path: Path) -> None:
    launcher = MatchLauncher(tmp_path, None, None)

    async def start_and_wait() -> None:
        launch = launcher.start(f"{BOT_MATCH}seed: 1\n")
        assert launch.status == "running"
        await launcher.wait()
        return

    asyncio.run(start_and_wait())
    [launch] = launcher.launches()
    assert (launch.status, launch.error) == ("finished", None)
    assert MatchStore(tmp_path).match(launch.match_id).status == "finished"
    with pytest.raises(ConfigError):
        launcher.start("- a list, not a config\n")
    return


def test_a_paused_match_holds_until_resumed(tmp_path: Path) -> None:
    launcher = MatchLauncher(tmp_path, None, None)

    async def pause_resume() -> None:
        match_id = launcher.start(BOT_MATCH).match_id
        assert launcher.pause(match_id).status == "paused"
        await asyncio.sleep(0.05)
        assert MatchStore(tmp_path).match(match_id).steps == 0
        assert launcher.resume(match_id).status == "running"
        await launcher.wait()
        assert launcher.launch(match_id).status == "finished"
        return

    asyncio.run(pause_resume())
    return


def test_a_stopped_match_ends_its_log_as_stopped(tmp_path: Path) -> None:
    launcher = MatchLauncher(tmp_path, None, None)

    async def pause_stop() -> str:
        match_id = launcher.start(BOT_MATCH).match_id
        launcher.pause(match_id)
        await asyncio.sleep(0.05)
        assert (await launcher.stop(match_id)).status == "stopped"
        return match_id

    match_id = asyncio.run(pause_stop())
    assert MatchStore(tmp_path).match(match_id).status == "stopped"
    return


def test_start_endpoint_offers_examples_and_rejects_bad_configs(tmp_path: Path) -> None:
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "ttt.yaml").write_text("game: k_in_a_row\n", encoding="utf-8")
    launcher = MatchLauncher(tmp_path / "runs", None, examples)
    client = TestClient(create_app(MatchStore(tmp_path / "runs"), launcher))
    assert client.get("/api/examples").json() == [
        {"name": "ttt", "text": "game: k_in_a_row\n"}
    ]
    assert client.post("/api/matches", json={"yaml": "- list"}).status_code == 422
    started = client.post("/api/matches", json={"yaml": BOT_MATCH})
    assert started.status_code == 201
    match_id = started.json()["match_id"]
    assert client.get("/api/launches").json()[0]["match_id"] == match_id
    for action in ("pause", "resume", "stop"):
        assert client.post(f"/api/launches/{match_id}/{action}").status_code == 200
    assert client.post("/api/launches/nope/stop").status_code == 404
    return
