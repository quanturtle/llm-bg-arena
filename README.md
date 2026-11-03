# Boardgames

Seat language models at the same board game table, and keep a replayable record of every move.

Each game's rules are written once in Python. Every seat is a language model available through OpenRouter; a seat that names none plays `qwen/qwen3.7-flash`. Every match writes a log with each move, what each player could see, and each model's reasoning, notes, retries, tokens and cost. A replay command rebuilds the match from its seed and checks the log move by move.

## Status

Early. Three games ship today:

- **Tic-tac-toe**: two players on a 3x3 board; three in a row wins.
- **Catan**: the standard 19-hex base game for 3 or 4 players, with settlements, cities, roads, harbours, trading, the robber and development cards.
- **Puerto Rico**: the standard base game for 3 to 5 players, with roles, plantations, buildings, colonists, trading and shipping.

Tournaments come next.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). The web viewer also needs Node.js 20.9+ and [pnpm](https://pnpm.io/) to build it once.

```sh
git clone <repo-url> boardgames
cd boardgames
uv sync
pnpm --dir web install
pnpm --dir web build
```

## Play

Players are language models on OpenRouter, so you need a key. Create a file named `.env` in the project folder with one line, `OPENROUTER_API_KEY=<your-key>`.

A match is described by a YAML file: the game, its config, and one entry per player with its model and that model's settings. Two cheap models at tic-tac-toe, from `examples/tic_tac_toe.yaml`:

```yaml
game: tic_tac_toe
seed: 7
seats:
  - model: qwen/qwen3.7-flash    # reasoning is off unless a seat asks for it
  - model: openai/gpt-5-nano
    reasoning_effort: low     # this model must think; low keeps replies short
```

```sh
uv run arena play examples/tic_tac_toe.yaml
```

That match costs well under a cent. Any OpenRouter model id works, and a seat without a `model` plays `qwen/qwen3.7-flash`; leave `seats` out and every player does. Each seat can set `temperature`, `top_p`, `max_tokens`, `reasoning` (`true` or `false`; off unless the seat sets it or asks for an effort or budget), `reasoning_effort` (`minimal`, `low`, `medium`, `high`, `xhigh`, `max`; each model takes only some) or `thinking_budget_tokens`, `verbosity` (answer length: `low` to `max`, for models that take it), `timeout_seconds`, `label`, `persona`, retries after an illegal move (`max_illegal_retries`), what to do when retries run out (`fallback`), an `extractor` model that rescues malformed replies, and `extra`, options passed to OpenRouter as they are. `output_mode: tools` lets the model inspect the game through tools (state, rules, legal actions, a legality check) before it acts, with `max_tool_calls` per decision; the default mode shows it the legal actions and asks for one answer. A player is called by its `label`, or else by its model; players on the same model become `qwen/qwen3.7-flash #1`, `qwen/qwen3.7-flash #2`. `cache: true` at the top of the file reuses stored replies for identical requests. `--seed` and `--log` override the file. The files in `examples/` also cover short three-player Catan and Puerto Rico games between cheap models.

Some models think before they answer, and that thinking counts toward `max_tokens` (default 4096). Reasoning is off by default, which keeps moves fast: `qwen/qwen3.7-flash` ignores `low` and token budgets and can think for minutes on one move. `openai/gpt-5-nano` must think and rejects reasoning off, so give it `reasoning_effort: low`.

Puerto Rico follows the role-selection cycle: the governor chooses first, every role's action phase runs immediately, and unchosen roles gain a doubloon at round end. `victory_point_supply` can lower the standard 75/100/122 chip supply for short games, and `max_rounds` adds a round limit. The full notation, buildings and scoring are in `boardgames/games/puerto_rico/rules.md`.

Catan uses the standard board and costs. Player-to-player trades are one card for one card, development cards are played after the roll, and offers are capped per turn to keep games moving; the full notation and rules are in the game's `rules.md`.

## Check a match

Every match writes two files to `runs/`: a JSONL log, and next to it a `.thoughts.md` you can read while the match runs, with each model's reasoning, tool calls, rejected answers and notes per move. Replaying the log rebuilds the game from the seed and compares every move, observation and event:

```console
$ uv run arena play examples/tic_tac_toe.yaml --log runs/demo.jsonl
tic_tac_toe (seed 7): P1 qwen/qwen3.7-flash, P2 openai/gpt-5-nano
    New game of tic-tac-toe.
[1] P1 qwen/qwen3.7-flash: b2
      reasoning: This is the first move of the game. I will choose the center square (b2) as it is the most strategic position, ...
    P1 (X) marked b2.
[2] P2 openai/gpt-5-nano: c3
      reasoning: I will block the key diagonal threat from X. With X at b2, the diagonal a1-b2-c3 could lead to a win for X ...
    P2 (O) marked c3.
...
[7] P1 qwen/qwen3.7-flash: b1
      reasoning: I have X at a1, b2, and c1. The bottom row (row 1) consists of cells a1, b1, and c1. ...
      rejected: The tool call needs a non-empty "action" string.
    P1 (X) marked b1.
    P1 (X) completed a line: a1 b1 c1.
Finished after 7 steps.
  #1 P1 qwen/qwen3.7-flash: 1 point (14508 tokens, $0.0007)
  #2 P2 openai/gpt-5-nano: 0 points (5021 tokens, $0.0013)
Ranks: P1 #1, P2 #2
Log: runs/demo.jsonl
Thoughts: runs/demo.thoughts.md

$ uv run arena replay runs/demo.jsonl
Replay matches the log: tic_tac_toe, 7 steps, 9 events.
```

## Watch

The web viewer lists every match in `runs/`, replays it move by move, and starts new ones: the "New match" page is a form where you pick the game and its settings, add players, and set each player's model, whether it reasons before moving, and other model settings. The form reads OpenRouter's model list, offers only the settings each model accepts, and starts cheap: reasoning off where a model allows it, otherwise its lowest effort. A started match runs inside the server, so the viewer follows it live. Its page has Pause, Resume and Stop buttons: pausing waits for the move in progress, and stopping ends the match at once and keeps its log. A match that is not playing can be deleted from its page or from the Matches list; that removes its log and thoughts file from `runs/`. Language model seats use the server's `OPENROUTER_API_KEY`.

```sh
uv run arena serve
```

Open http://127.0.0.1:8000/. Each replay shows the board at every step (a drawn board for tic-tac-toe, Catan and Puerto Rico), what the deciding model was asked, what it answered, its reasoning and notes, any rejected attempts, and points over time. Stepping through a match keeps every panel in place: the board, the players and the event log hold their size from the first step to the last. Private events can be shown for one seat or for everyone. A match that is still running is updated as its log grows. The leaderboard ranks agents per game by Elo, with win rate, average rank, forfeits, the share of rejected answers, latency, tokens and cost per match; each agent has a page with its record per game and against each opponent. Each game has a page with its rules, default config, standings and matches. `--runs` points at another log directory, `--port` changes the port, and `--viewer` points at another viewer build (default `web/out`). Without a build, `arena serve` stops and prints the command that makes one.

## Develop

```sh
uv run pytest
uv run ruff check .
uv run mypy
pnpm --dir web lint
pnpm --dir web build
```

To work on the viewer with live reload, keep `uv run arena serve` running and start `pnpm --dir web dev`, then open http://localhost:3000/. The dev server sends `/api` requests to port 8000. After an API change, `pnpm --dir web gen:api` regenerates the viewer's API types from the running server.

How games, players and logs fit together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
