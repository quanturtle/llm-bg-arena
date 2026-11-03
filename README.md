# Boardgames

Seat language models, scripted bots and humans at the same board game table, and keep a replayable record of every move.

Each game's rules are written once in Python. Any kind of player can then take a seat: a random bot, or a language model from Anthropic, OpenAI, OpenRouter or any other provider LiteLLM supports. Every match writes a log with each move, what each player could see, and each model's reasoning, notes, retries, tokens and cost. A replay command rebuilds the match from its seed and checks the log move by move.

## Status

Early. Two small games ship today:

- **k-in-a-row**: tic-tac-toe by default, plus four-in-a-row and other board sizes.
- **Sealed auction**: 2 to 4 players bid coins in secret for lots, with a secret scoring color each.

Larger strategy games, tournaments, ratings and a web replay viewer come next.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone <repo-url> boardgames
cd boardgames
uv sync
```

## Play

Two random bots at tic-tac-toe:

```sh
uv run arena play k_in_a_row --seed 7
```

A language model against a random bot. First create a file named `.env` in the project folder with one line, `ANTHROPIC_API_KEY=<your-key>` (or `OPENAI_API_KEY`, `OPENROUTER_API_KEY`). Then:

```sh
uv run arena play k_in_a_row --agent llm:anthropic/claude-haiku-5-5 --agent random
```

Any LiteLLM model id works after `llm:`. Four-in-a-row and a four-player auction:

```sh
uv run arena play k_in_a_row --config '{"rows": 6, "cols": 7, "k": 4, "gravity": true}'
uv run arena play sealed_auction --config '{"num_players": 4}'
```

`uv run arena play --help` lists the model options: temperature, retries after an illegal move, what to do when retries run out, response caching.

## Check a match

Every match writes a log to `runs/`. Replaying it rebuilds the game from the seed and compares every move, observation and event:

```console
$ uv run arena play k_in_a_row --seed 7 --log runs/demo.jsonl
k_in_a_row (seed 7): P1 random, P2 random
    New game: 3 in a row on 3x3.
[1] P1 random: a2
    P1 (X) marked a2.
[2] P2 random: a3
    P2 (O) marked a3.
...
[6] P2 random: c3
    P2 (O) marked c3.
    P2 (O) completed a line: a3 b3 c3.
Finished after 6 steps.
  #1 P2 random: 1 point
  #2 P1 random: 0 points
Ranks: P1 #2, P2 #1
Log: runs/demo.jsonl

$ uv run arena replay runs/demo.jsonl
Replay matches the log: k_in_a_row, 6 steps, 8 events.
```

## Develop

```sh
uv run pytest
uv run ruff check .
uv run mypy
```

How games, players and logs fit together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
