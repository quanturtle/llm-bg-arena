from pathlib import Path

from fastapi.testclient import TestClient

from boardgames.arena.match_config import DEFAULT_MODEL
from boardgames.llm.catalog import ModelCapabilities, ReasoningSupport
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore

QWEN = ModelCapabilities(
    id=DEFAULT_MODEL,
    name="Qwen",
    parameters=["reasoning", "temperature", "tools"],
    reasoning=ReasoningSupport(is_mandatory=False, efforts=[], default_effort=None),
    max_output_tokens=65536,
    default_temperature=None,
)


class OneModelCatalog:
    """A catalog that lists only the default model."""

    async def lookup(self, model_id: str) -> ModelCapabilities | None:
        return QWEN if model_id == DEFAULT_MODEL else None


def options_client(tmp_path: Path) -> TestClient:
    launcher = MatchLauncher(tmp_path, None, None)
    return TestClient(create_app(MatchStore(tmp_path), launcher, OneModelCatalog()))


def test_match_options_list_seat_counts_settings_and_models(tmp_path: Path) -> None:
    body = options_client(tmp_path).get("/api/match-options").json()
    games = {game["id"]: game for game in body["games"]}
    assert games["catan"]["player_counts"] == [3, 4]
    assert games["puerto_rico"]["player_counts"] == [3, 4, 5]
    assert games["terra_mystica"]["player_counts"] == [2, 3, 4, 5]
    assert (games["catan"]["name"], games["catan"]["summary"][:8]) == (
        "Catan",
        "Be first",
    )
    assert "num_players" not in games["catan"]["settings"]
    assert body["default_model"] == DEFAULT_MODEL
    assert DEFAULT_MODEL in body["models"]
    assert body["seat_defaults"]["max_illegal_retries"] == 3
    assert list(body["capabilities"]) == [DEFAULT_MODEL]
    assert body["capabilities"][DEFAULT_MODEL]["max_output_tokens"] == 65536
    return


def test_model_capabilities_answer_404_for_unlisted_models(tmp_path: Path) -> None:
    client = options_client(tmp_path)
    found = client.get("/api/model-capabilities", params={"model": DEFAULT_MODEL})
    assert found.json()["name"] == "Qwen"
    assert client.get("/api/model-capabilities?model=no/such").status_code == 404
    return
