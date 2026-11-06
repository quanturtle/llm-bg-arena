# LLM Boardgame Arena

![A Catan replay in the viewer: the board, each player's cards, the deciding model's reasoning and notes, and the event log](img/llm-bg-arena.png)

Put a few LLMs around a board game table and watch them play. Every move is logged with what the model saw, what it was thinking and what it cost, so you can replay any match step by step.

Games: **Catan** (3–4 players), **Puerto Rico** (3–5), **Terra Mystica** (2–5) and **tic-tac-toe** for quick tests. Each game's rules are in its `rules.md`, for example `boardgames/games/catan/rules.md`.

## Run it

You'll need Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20.9+ and [pnpm](https://pnpm.io/). Every player is a model on [OpenRouter](https://openrouter.ai/), so put your key in a `.env` file in the project folder:

```
OPENROUTER_API_KEY=<your-key>
```

Then start the arena:

```sh
uv run arena serve
```

Open http://127.0.0.1:8765/. The first start installs and builds the viewer; later starts skip that until something in `web/` changes. In the viewer you can:

- Start a match: pick a game and a model for each seat.
- Watch it live, and pause, resume or stop it.
- Replay any match step by step, with each model's reasoning and notes.
- Compare models on the Elo leaderboard.

## An example game

```sh
uv run arena serve examples/catan_game.jsonl
```

This opens the browser on a full Catan game to 10 points between Claude Haiku 5.5, DeepSeek V4.1 Flash and GPT-6 Luna. It took 811 moves, 35 minutes and $0.61, and GPT-6 Luna won 10–8–4. No key is needed to watch it.

## Credits

- Puerto Rico cards, tiles, barrels and boards: [Middlederg/puerto-rico](https://github.com/Middlederg/puerto-rico). That repo doesn't declare a licence.
- Catan terrain and sea art: [baige007/Catan-web-game-](https://github.com/baige007/Catan-web-game-) (MIT), which builds on [Erodenn/Simple-Catan](https://github.com/Erodenn/Simple-Catan).
- Catan port and robber icons: [game-icons.net](https://game-icons.net/), by Delapouite and Lorc (CC BY 3.0).
- Model provider logos: [lobehub/lobe-icons](https://github.com/lobehub/lobe-icons) (MIT).

`web/public/puerto_rico/SOURCE.md` and `web/public/catan/SOURCE.md` say where each file came from.
