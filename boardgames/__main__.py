"""Entry point for `python -m boardgames`."""

from boardgames.arena import cli


def main() -> None:
    cli.main()
    return


if __name__ == "__main__":
    main()
