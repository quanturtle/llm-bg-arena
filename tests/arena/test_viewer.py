from pathlib import Path

from boardgames.arena.viewer import build_viewer, viewer_is_stale


class FakePnpm:
    """Records build commands and writes the page a real build would."""

    def __init__(self, sources: Path) -> None:
        self.commands: list[list[str]] = []
        self._sources = sources
        return

    def __call__(self, command: list[str]) -> int:
        self.commands.append(command)
        (self._sources / "out").mkdir(exist_ok=True)
        (self._sources / "out" / "index.html").write_text("<html></html>")
        return 0


def test_viewer_rebuilds_only_after_its_sources_change(tmp_path: Path) -> None:
    sources = tmp_path / "web"
    (sources / "src").mkdir(parents=True)
    (sources / "package.json").write_text("{}")
    (sources / "src" / "page.tsx").write_text("first")
    pnpm = FakePnpm(sources)

    assert viewer_is_stale(sources)
    build_viewer(sources, pnpm)
    assert [command[3] for command in pnpm.commands] == ["install", "build"]
    assert not viewer_is_stale(sources)

    (sources / "src" / "page.tsx").write_text("second")
    assert viewer_is_stale(sources)
