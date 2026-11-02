"""Entry point for `python -m tabletop_arena`."""

from tabletop_arena.arena import cli


def main() -> None:
    cli.main()
    return


if __name__ == "__main__":
    main()
