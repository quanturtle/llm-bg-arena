# Boardgames

Seat language models, scripted bots and humans at the same board game table, and keep a replayable record of every move.

Each game's rules are written once in Python. Any kind of player can then take a seat: a random bot, or a language model from Anthropic, OpenAI, OpenRouter or any other provider LiteLLM supports. Every match writes a log with each move, what each player could see, and each model's reasoning, notes, retries, tokens and cost. A replay command rebuilds the match from its seed and checks the log move by move.

## Status

Early. Three games ship today:

- **k-in-a-row**: tic-tac-toe by default, plus four-in-a-row and other board sizes.
- **Sealed auction**: 2 to 4 players bid coins in secret for lots, with a secret scoring color each.
- **Catan**: the standard 19-hex base game for 3 or 4 players, with settlements, cities, roads, harbours, trading, the robber and development cards.

Tournaments, ratings and a web replay viewer come next.

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

Any LiteLLM model id works after `llm:`. Four-in-a-row, a four-player auction, and a short three-player Catan game:

```sh
uv run arena play k_in_a_row --config '{"rows": 6, "cols": 7, "k": 4, "gravity": true}'
uv run arena play sealed_auction --config '{"num_players": 4}'
uv run arena play catan --config '{"num_players": 3, "victory_points": 6}'
```

Catan uses the standard board and costs. Player-to-player trades are one card for one card, development cards are played after the roll, and offers are capped per turn to keep games moving; the full notation and rules are in the game's `rules.md`.

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

## Watch

The web viewer lists every match in `runs/` and replays it move by move:

```sh
uv run arena serve
```

Open http://127.0.0.1:8000/. Each replay shows the board at every step (a drawn board for k-in-a-row, the auction and Catan, the text view otherwise), what the deciding model was asked, what it answered, its reasoning and notes, any rejected attempts, and points over time. Private events can be shown for one seat or for everyone. A match that is still running is updated as its log grows. The leaderboard ranks agents per game by Elo, with win rate, average rank, forfeits, the share of rejected answers, latency, tokens and cost per match; each agent has a page with its record per game and against each opponent. Each game has a page with its rules, default config, standings and matches. `--runs` points at another log directory and `--port` changes the port.

## Develop

```sh
uv run pytest
uv run ruff check .
uv run mypy
```

How games, players and logs fit together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
