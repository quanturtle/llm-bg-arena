# LLM Boardgame Arena

![A Catan replay in the viewer: the board, each player's cards, the deciding model's reasoning and notes, and the event log](img/llm-bg-arena.png)

Put a few LLMs around a board game table and watch them play. Every move is logged with what the model saw, what it was thinking and what it cost, so you can replay any match step by step.

Games: **Catan** (3–4 players), **Puerto Rico** (3–5), **Terra Mystica** (2–5) and **tic-tac-toe** for quick tests. Each game's rules and move notation are in its `rules.md`, for example `boardgames/games/catan/rules.md`.

## Setup

You'll need Python 3.12+ and [uv](https://docs.astral.sh/uv/). The viewer also needs Node.js 20.9+ and [pnpm](https://pnpm.io/).

```sh
git clone <repo-url> llm-bg-arena
cd llm-bg-arena
uv sync
pnpm --dir web install
pnpm --dir web build
```

Every player is a model on [OpenRouter](https://openrouter.ai/). Put your key in a `.env` file in the project folder:

```
OPENROUTER_API_KEY=<your-key>
```

## Play a match

A match is a small YAML file: the game, a seed, and who sits where. This is `examples/catan.yaml`, three cheap models racing to 5 points:

```yaml
game: catan
config: {num_players: 3, victory_points: 5}
seed: 1
seats:
  - model: qwen/qwen3.7-flash
  - model: deepseek/deepseek-v4.1-flash
    reasoning_effort: low
  - model: z-ai/glm-5.3-flash
    reasoning_effort: low
```

```sh
uv run arena play examples/catan.yaml
```

Any OpenRouter model id works. A seat with no `model` gets `qwen/qwen3.7-flash`. The settings you'll reach for most:

| Setting | What it does |
| --- | --- |
| `reasoning_effort` | Let the model think before it moves. Off unless you set it. |
| `label`, `persona` | A display name, and extra instructions like "play cautiously and trade often". |
| `output_mode: tools` | Let the model look up the state, the rules and the legal moves through tool calls before it answers. |
| `fallback` | What happens after repeated illegal moves: a random move, the game's default move, or a forfeit. |

Every setting is listed in `LlmOptions` in `boardgames/arena/match_config.py`.

## An example game

`examples/catan_game.jsonl` is a full Catan game to 10 points between Claude Haiku 5.5, DeepSeek V4.1 Flash and GPT-6 Luna. It took 811 moves, 35 minutes and $0.61. `examples/catan_game.thoughts.md` has every model's reasoning in readable form. This is the start and end of what the console printed:

```console
catan (seed 271366): P1 anthropic/claude-haiku-5.5, P2 deepseek/deepseek-v4.1-flash, P3 openai/gpt-6-luna
    New game: Catan for 3 players; first to 10 victory points wins.
    The board is set; the robber starts on the desert h14.
    P1 places a settlement, then a road.
[1] P1 anthropic/claude-haiku-5.5: settle v14
      reasoning: Pick a strong intersection with high-probability numbers. v14 touches 10, 9, 4 (mountains, pasture, forest) — good mix. ...
    P1 placed a settlement on v14.
...
[807] P3 openai/gpt-6-luna: offer wheat for sheep to P1
      reasoning: A settlement immediately wins, but the hand lacks sheep. Offer wheat for sheep to P1; ...
    P3 offers P1 1 wheat for 1 sheep.
[808] P1 anthropic/claude-haiku-5.5: accept
      reasoning: Accepting gives me wheat (needed for settlements/cities/dev). P3 is not the leader (P2 is at 7VP, P3 at 5). ...
    P1 accepted: P3 gave 1 wheat for 1 sheep.
[809] P3 openai/gpt-6-luna: road e1
      reasoning: The settlement sites on my network are blocked by the distance rule. ...
      rejected: v12 is adjacent to another building.
      rejected: v13 is adjacent to another building.
    P3 built a road on e1.
[810] P3 openai/gpt-6-luna: bank 4 wheat for 1 brick
      reasoning: At 9 VP and no legal immediate scoring build visible, use the wheat surplus to acquire brick for a settlement, ...
    P3 traded 4 wheat for 1 brick with the bank.
[811] P3 openai/gpt-6-luna: settle v0
      reasoning: A settlement immediately brings P3 to 10 VP; v0 is the only listed legal settlement site.
    P3 built a settlement on v0.
    P3 wins with 10 victory points.
Finished after 811 steps.
  #1 P3 openai/gpt-6-luna: 10 points (1504253 tokens, $0.1473)
  #2 P2 deepseek/deepseek-v4.1-flash: 8 points (1807105 tokens, $0.2103)
  #3 P1 anthropic/claude-haiku-5.5: 4 points (2259352 tokens, $0.2539)
```

P3 had four hidden victory point cards, so P1 saw only 5 of its 9 points when it accepted that trade.

`arena replay` rebuilds a match from its seed and checks the log move by move:

```console
$ uv run arena replay examples/catan_game.jsonl
Replay matches the log: catan, 811 steps, 1366 events.
```

## The viewer

```sh
uv run arena serve
```

Then open http://127.0.0.1:8765/. The viewer replays the matches in `runs/` step by step, keeps an Elo leaderboard per game, and starts new matches you can watch live. To step through the example game, run `uv run arena serve --runs examples`.

Your own matches land in `runs/`: a JSONL log and a `.thoughts.md` file per match.

## Development

```sh
uv run pytest
uv run ruff check .
uv run mypy
pnpm --dir web lint
pnpm --dir web build
```

For live reload on the viewer, leave `uv run arena serve` running, start `pnpm --dir web dev` and go to http://localhost:3000/.

## Credits

- Puerto Rico cards, tiles, barrels and boards: [Middlederg/puerto-rico](https://github.com/Middlederg/puerto-rico). That repo doesn't declare a licence.
- Catan terrain and sea art: [baige007/Catan-web-game-](https://github.com/baige007/Catan-web-game-) (MIT), which builds on [Erodenn/Simple-Catan](https://github.com/Erodenn/Simple-Catan).
- Catan port and robber icons: [game-icons.net](https://game-icons.net/), by Delapouite and Lorc (CC BY 3.0).
- Model provider logos: [lobehub/lobe-icons](https://github.com/lobehub/lobe-icons) (MIT).

`web/public/puerto_rico/SOURCE.md` and `web/public/catan/SOURCE.md` say where each file came from.
