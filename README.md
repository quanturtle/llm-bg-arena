# Boardgames

Seat language models and random bots at the same board game table, and keep a replayable record of every move.

Each game's rules are written once in Python. Two kinds of player can then take a seat: a random bot, or any language model available through OpenRouter. Every match writes a log with each move, what each player could see, and each model's reasoning, notes, retries, tokens and cost. A replay command rebuilds the match from its seed and checks the log move by move.

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

A match is described by a YAML file: the game, its config, and who sits at each seat. Two random bots at tic-tac-toe:

```sh
uv run arena play examples/tic_tac_toe.yaml
```

Language models need an OpenRouter key. Create a file named `.env` in the project folder with one line, `OPENROUTER_API_KEY=<your-key>`, then seat them in the file:

```yaml
game: sealed_auction
config: {num_players: 3}
llm:                       # defaults for every llm seat
  temperature: 0.2
  cache: true
seats:
  - agent: llm
    model: anthropic/claude-haiku-5-5
    reasoning_effort: high
  - agent: llm
    model: openai/gpt-5-mini
    extra: {provider: {order: [openai]}}
  - agent: random
```

```sh
uv run arena play examples/auction_llms.yaml
```

The example file is this config plus a fixed seed, `output_mode: tools`, seat labels, a `thinking_budget_tokens` for the second model, and some built-in defaults written out.

Any OpenRouter model id works. Under `llm` or per seat you can set `temperature`, `top_p`, `max_tokens`, `reasoning_effort` or `thinking_budget_tokens`, `timeout_seconds`, `persona`, retries after an illegal move (`max_illegal_retries`), what to do when retries run out (`fallback`), an `extractor` model that rescues malformed replies, and `extra`, options passed to OpenRouter as they are. `output_mode: tools` lets the model inspect the game through tools (state, rules, legal actions, a legality check) before it acts, with `max_tool_calls` per decision; the default mode shows it the legal actions and asks for one answer. Leave `seats` out to seat random bots everywhere. `--seed` and `--log` override the file. The files in `examples/` cover four-in-a-row, the auction and a short three-player Catan game.

Catan uses the standard board and costs. Player-to-player trades are one card for one card, development cards are played after the roll, and offers are capped per turn to keep games moving; the full notation and rules are in the game's `rules.md`.

## Check a match

Every match writes a log to `runs/`. Replaying it rebuilds the game from the seed and compares every move, observation and event:

```console
$ uv run arena play examples/tic_tac_toe.yaml --log runs/demo.jsonl
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
