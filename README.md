# Boardgames

Seat language models and random bots at the same board game table, and keep a replayable record of every move.

Each game's rules are written once in Python. Two kinds of player can then take a seat: a random bot, or any language model available through OpenRouter. Every match writes a log with each move, what each player could see, and each model's reasoning, notes, retries, tokens and cost. A replay command rebuilds the match from its seed and checks the log move by move.

## Status

Early. Three games ship today:

- **Tic-tac-toe**: two players on a 3x3 board; three in a row wins.
- **Catan**: the standard 19-hex base game for 3 or 4 players, with settlements, cities, roads, harbours, trading, the robber and development cards.
- **Puerto Rico**: the standard base game for 3 to 5 players, with roles, plantations, buildings, colonists, trading and shipping.

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

Language models need an OpenRouter key. Create a file named `.env` in the project folder with one line, `OPENROUTER_API_KEY=<your-key>`, then seat them in a file such as `match.yaml`:

```yaml
game: puerto_rico
config: {num_players: 3, max_rounds: 5}
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
uv run arena play match.yaml
```

Any OpenRouter model id works. Under `llm` or per seat you can set `temperature`, `top_p`, `max_tokens`, `reasoning_effort` or `thinking_budget_tokens`, `timeout_seconds`, `persona`, retries after an illegal move (`max_illegal_retries`), what to do when retries run out (`fallback`), an `extractor` model that rescues malformed replies, and `extra`, options passed to OpenRouter as they are. `output_mode: tools` lets the model inspect the game through tools (state, rules, legal actions, a legality check) before it acts, with `max_tool_calls` per decision; the default mode shows it the legal actions and asks for one answer. Leave `seats` out to seat random bots everywhere. `--seed` and `--log` override the file. The files in `examples/` cover tic-tac-toe and short three-player Catan and Puerto Rico games, all between random bots.

Puerto Rico follows the role-selection cycle: the governor chooses first, every role's action phase runs immediately, and unchosen roles gain a doubloon at round end. `victory_point_supply` can lower the standard 75/100/122 chip supply for short games, and `max_rounds` adds a round limit. The full notation, buildings and scoring are in `boardgames/games/puerto_rico/rules.md`.

Catan uses the standard board and costs. Player-to-player trades are one card for one card, development cards are played after the roll, and offers are capped per turn to keep games moving; the full notation and rules are in the game's `rules.md`.

## Check a match

Every match writes two files to `runs/`: a JSONL log, and next to it a `.thoughts.md` you can read while the match runs, with each model's reasoning, tool calls, rejected answers and notes per move. Replaying the log rebuilds the game from the seed and compares every move, observation and event:

```console
$ uv run arena play examples/tic_tac_toe.yaml --log runs/demo.jsonl
tic_tac_toe (seed 7): P1 random, P2 random
    New game of tic-tac-toe.
[1] P1 random: a2
    P1 (X) marked a2.
[2] P2 random: a3
    P2 (O) marked a3.
[3] P1 random: b1
    P1 (X) marked b1.
[4] P2 random: b3
    P2 (O) marked b3.
[5] P1 random: b2
    P1 (X) marked b2.
[6] P2 random: c3
    P2 (O) marked c3.
    P2 (O) completed a line: a3 b3 c3.
Finished after 6 steps.
  #1 P2 random: 1 point
  #2 P1 random: 0 points
Ranks: P1 #2, P2 #1
Log: runs/demo.jsonl
Thoughts: runs/demo.thoughts.md

$ uv run arena replay runs/demo.jsonl
Replay matches the log: tic_tac_toe, 6 steps, 8 events.
```

## Watch

The web viewer lists every match in `runs/`, replays it move by move, and starts new ones: the "New match" page is a form where you pick the game and its settings, add players, and set each player's model and model settings, and a started match runs inside the server, so the viewer follows it live. Its page has Pause, Resume and Stop buttons: pausing waits for the move in progress, and stopping ends the match at once and keeps its log. Language model seats use the server's `OPENROUTER_API_KEY`.

```sh
uv run arena serve
```

Open http://127.0.0.1:8000/. Each replay shows the board at every step (a drawn board for tic-tac-toe, Catan and Puerto Rico), what the deciding model was asked, what it answered, its reasoning and notes, any rejected attempts, and points over time. Private events can be shown for one seat or for everyone. A match that is still running is updated as its log grows. The leaderboard ranks agents per game by Elo, with win rate, average rank, forfeits, the share of rejected answers, latency, tokens and cost per match; each agent has a page with its record per game and against each opponent. Each game has a page with its rules, default config, standings and matches. `--runs` points at another log directory and `--port` changes the port.

## Develop

```sh
uv run pytest
uv run ruff check .
uv run mypy
```

How games, players and logs fit together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
