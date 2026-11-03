from pathlib import Path

from fastapi.testclient import TestClient

from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore


def test_health_answers_ok(tmp_path: Path) -> None:
    app = create_app(MatchStore(tmp_path), MatchLauncher(tmp_path, None, None))
    assert TestClient(app).get("/health").json() == {"status": "ok"}
    return
