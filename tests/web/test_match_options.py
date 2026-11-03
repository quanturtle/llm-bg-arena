from pathlib import Path

from fastapi.testclient import TestClient

from boardgames.arena.match_config import DEFAULT_MODEL
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore


def test_match_options_list_seat_counts_settings_and_models(tmp_path: Path) -> None:
    launcher = MatchLauncher(tmp_path, None, None)
    options = TestClient(create_app(MatchStore(tmp_path), launcher)).get(
        "/api/match-options"
    )
    body = options.json()
    games = {game["id"]: game for game in body["games"]}
    assert games["catan"]["player_counts"] == [3, 4]
    assert "num_players" not in games["catan"]["settings"]
    assert body["default_model"] == DEFAULT_MODEL
    assert DEFAULT_MODEL in body["models"]
    return
