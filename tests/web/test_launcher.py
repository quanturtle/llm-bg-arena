import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgames.core import ConfigError
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore


def test_launcher_starts_a_match_and_reports_how_it_ended(tmp_path: Path) -> None:
    launcher = MatchLauncher(tmp_path, None, None)

    async def start_and_wait() -> None:
        launch = launcher.start("game: k_in_a_row\nseed: 1\n")
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
    started = client.post("/api/matches", json={"yaml": "game: k_in_a_row\n"})
    assert started.status_code == 201
    assert (
        client.get("/api/launches").json()[0]["match_id"] == started.json()["match_id"]
    )
    return
