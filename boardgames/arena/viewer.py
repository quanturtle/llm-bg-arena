"""Keep the built web viewer in step with its sources.

`arena serve` checks the viewer before serving it. The build stores a SHA-256
digest of the viewer sources; a missing build or a different digest means
`pnpm install` and `pnpm build` run again, otherwise the server starts at once.
"""

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from boardgames.core import ArenaError

BUILD_DIRECTORY = "out"
DIGEST_FILE = ".sources.sha256"
# written by pnpm, Next.js and TypeScript during a build, so not sources
GENERATED_DIRECTORIES = frozenset({"node_modules", BUILD_DIRECTORY, ".next"})
GENERATED_FILES = frozenset({"next-env.d.ts", ".DS_Store"})
GENERATED_SUFFIX = ".tsbuildinfo"
BUILD_STEPS: tuple[tuple[str, ...], ...] = (
    ("install", "--frozen-lockfile"),
    ("build",),
)

type CommandRunner = Callable[[list[str]], int]


class ViewerBuildError(ArenaError):
    """The viewer could not be built."""


def viewer_is_stale(sources: Path) -> bool:
    """True when `sources` has a viewer that is unbuilt or built from older sources."""
    if not (sources / "package.json").is_file():
        return False
    build = sources / BUILD_DIRECTORY
    if not (build / "index.html").is_file() or not (build / DIGEST_FILE).is_file():
        return True
    return (build / DIGEST_FILE).read_text(encoding="utf-8") != source_digest(sources)


def source_digest(sources: Path) -> str:
    """SHA-256 over the relative path and content hash of every source file."""
    digest = hashlib.sha256()
    for path in source_files(sources):
        content = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(f"{path.relative_to(sources).as_posix()}\0{content}\n".encode())
    return digest.hexdigest()


def source_files(sources: Path) -> list[Path]:
    """Every file under `sources` except build output and dependencies, sorted."""
    files: list[Path] = []
    for directory, subdirectories, names in sources.walk():
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in GENERATED_DIRECTORIES
        )
        files.extend(
            directory / name
            for name in sorted(names)
            if name not in GENERATED_FILES and not name.endswith(GENERATED_SUFFIX)
        )
    return files


def build_viewer(sources: Path, run: CommandRunner) -> None:
    """Install the viewer's packages, build it, and record its sources' digest."""
    digest = source_digest(sources)
    for step in BUILD_STEPS:
        command = ["pnpm", "--dir", str(sources), *step]
        status = run(command)
        if status != 0:
            raise ViewerBuildError(
                f"`{' '.join(command)}` failed with exit status {status}"
            )
    (sources / BUILD_DIRECTORY / DIGEST_FILE).write_text(digest, encoding="utf-8")
    return


def run_build_command(command: list[str]) -> int:
    """Run one build step with its output on the terminal; return its exit status."""
    if shutil.which(command[0]) is None:
        raise ViewerBuildError(
            f"building the viewer needs {command[0]}: install Node.js 20.9+ and pnpm"
        )
    return subprocess.run(command, check=False).returncode
