// New match page: choose a game, its options and a model per player, then start the match.
(function () {
  const { h, api, send, setActiveNav, routes, app } = window.viewer;

  // How each game option reads in the form; unknown options get a label from their key.
  const GAME_OPTIONS = {
    "catan.victory_points": { label: "Points to win", hint: "10 is the standard game; 5 or 6 makes a shorter one.", min: 3, max: 20 },
    "catan.max_offers_per_turn": { label: "Trade offers per turn", hint: "0 means no limit.", min: 0, max: 20 },
    "puerto_rico.victory_point_supply": { label: "Victory point chips", hint: "0 uses the standard supply; fewer chips end the game sooner.", min: 0 },
    "puerto_rico.max_rounds": { label: "Round limit", hint: "0 plays to the normal end of the game.", min: 0 },
  };

  const PROVIDERS = { anthropic: "Anthropic", deepseek: "DeepSeek", google: "Google", mistralai: "Mistral", openai: "OpenAI", qwen: "Qwen", "z-ai": "Z.ai" };

  // Per-player settings, in plain words; an empty field keeps the default shown in it.
  const SEAT_FIELDS = [
    { key: "label", label: "Name", kind: "text", hint: "Defaults to the model; players on the same model get #1, #2." },
    { key: "reasoning", label: "Reasoning", kind: "toggle", hint: "Lets the model think before it moves. Off is much faster; some models (like gpt-5-nano) can't turn it off." },
    { key: "reasoning_effort", label: "Reasoning effort", kind: "select", options: [["low", "Low"], ["medium", "Medium"], ["high", "High"]], needsReasoning: true },
    { key: "temperature", label: "Randomness (temperature)", kind: "number", step: "0.1", min: "0", max: "2", hint: "0 is steady and predictable, 1 or more is varied." },
    { key: "max_tokens", label: "Longest reply (tokens)", kind: "number", step: "1", min: "1", hint: "Reasoning counts toward it." },
    { key: "max_illegal_retries", label: "Second chances after an illegal move", kind: "number", step: "1", min: "0" },
    { key: "fallback", label: "If it still can't move", kind: "select", options: [["random", "Play a random legal move"], ["default", "Play the game's default move"], ["forfeit", "Forfeit the match"]] },
    { key: "timeout_seconds", label: "Time limit per reply (seconds)", kind: "number", step: "1", min: "1" },
    { key: "top_p", label: "Top p", kind: "number", step: "0.05", min: "0", max: "1", hint: "Usually left alone." },
    { key: "persona", label: "Personality and extra instructions", kind: "textarea", hint: "For example: play cautiously and trade often." },
  ];

  function humanize(key) {
    const words = key.replace(/_/g, " ");
    return words.charAt(0).toUpperCase() + words.slice(1);
  }

  function modelName(id) {
    const [provider, name] = id.includes("/") ? id.split("/", 2) : ["", id];
    return provider ? `${name} (${PROVIDERS[provider] || provider})` : id;
  }

  function playerRange(counts) {
    const low = counts[0];
    const high = counts[counts.length - 1];
    return low === high ? `${low} players` : `${low} to ${high} players`;
  }

  function launchRow(launch) {
    const link = h("a", { href: `#/match/${launch.match_id}` }, launch.match_id);
    const badge = h("span", { class: `badge ${launch.status}` }, launch.status);
    return h("li", {}, link, " ", badge, launch.error ? h("span", { class: "error" }, ` ${launch.error}`) : null);
  }

  function newSeat(state) {
    return { model: state.options.default_model, custom: false, reasoning: state.options.seat_defaults.reasoning === true, settings: {} };
  }

  function currentGame(state) {
    return state.options.games.find((game) => game.id === state.game);
  }

  // Keep the players already set up, within the counts the game allows.
  function fitSeats(state) {
    const counts = currentGame(state).player_counts;
    const target = Math.min(Math.max(state.seats.length, counts[0]), counts[counts.length - 1]);
    state.seats = state.seats.slice(0, target);
    while (state.seats.length < counts[0]) state.seats.push(newSeat(state));
  }

  // The match config sent to the server: only what the user filled in.
  function matchConfig(state, seed) {
    const config = { num_players: state.seats.length };
    for (const [key, value] of Object.entries(state.settings)) {
      if (value !== undefined) config[key] = value;
    }
    const seats = state.seats.map((seat) => {
      const entry = { model: seat.model.trim() || state.options.default_model };
      for (const [key, value] of Object.entries(seat.settings)) {
        if (value !== undefined) entry[key] = value;
      }
      // reasoning and its effort are separate settings; an effort only goes with reasoning on
      entry.reasoning = seat.reasoning;
      if (!seat.reasoning) delete entry.reasoning_effort;
      return entry;
    });
    return { game: state.game, config, seed, seats };
  }

  function defaultText(state, key, field) {
    const value = state.options.seat_defaults[key];
    if (value === null || value === undefined) return "model's default";
    const option = field.options && field.options.find(([code]) => code === value);
    return option ? option[1] : String(value);
  }

  function defaultLabel(text) {
    return text === "model's default" ? text : `${text} (default)`;
  }

  function seatInput(state, field, seat, changed, rerender) {
    const current = seat.settings[field.key];
    const update = (raw) => {
      seat.settings[field.key] = raw === "" ? undefined : field.kind === "number" ? Number(raw) : raw;
      changed();
    };
    if (field.kind === "toggle") {
      const box = h("input", { type: "checkbox", onchange: (event) => { seat.reasoning = event.target.checked; rerender(); } });
      box.checked = seat.reasoning;
      return h("span", { class: "toggle" }, box, seat.reasoning ? "On" : "Off");
    }
    if (field.kind === "select") {
      const off = field.needsReasoning && !seat.reasoning;
      const select = h("select", { disabled: off ? "" : null, onchange: (event) => update(event.target.value) }, h("option", { value: "" }, off ? "Reasoning is off" : defaultLabel(defaultText(state, field.key, field))), field.options.filter(([code]) => code !== state.options.seat_defaults[field.key]).map(([code, text]) => h("option", { value: code }, text)));
      select.value = current === undefined || off ? "" : String(current);
      return select;
    }
    if (field.kind === "textarea") {
      const area = h("textarea", { rows: 2, placeholder: field.hint || "", oninput: (event) => update(event.target.value) });
      area.value = current === undefined ? "" : current;
      return area;
    }
    const fallback = defaultText(state, field.key, field);
    const placeholder = field.key === "label" ? "the model's name" : fallback.startsWith("model") ? fallback : `default: ${fallback}`;
    const input = h("input", { type: field.kind, step: field.step, min: field.min, max: field.max, placeholder, oninput: (event) => update(event.target.value) });
    input.value = current === undefined ? "" : String(current);
    return input;
  }

  function modelPicker(state, seat, changed, rerender) {
    const known = state.options.models;
    const select = h("select", {
      onchange: (event) => {
        if (event.target.value === "__other") {
          seat.custom = true;
          seat.model = "";
        } else {
          seat.custom = false;
          seat.model = event.target.value;
        }
        rerender();
      },
    },
    known.map((id) => h("option", { value: id }, `${modelName(id)}${id === state.options.default_model ? " · default" : ""}`)),
    h("option", { value: "__other" }, "Another OpenRouter model…"));
    select.value = seat.custom || !known.includes(seat.model) ? "__other" : seat.model;
    const other = seat.custom || !known.includes(seat.model)
      ? h("input", { type: "text", value: seat.model, placeholder: "provider/model, for example meta-llama/llama-4-scout", oninput: (event) => { seat.model = event.target.value; changed(); } })
      : null;
    return h("div", { class: "model-picker" }, select, other);
  }

  function seatCard(state, seat, index, changed, rerender) {
    const removable = state.seats.length > currentGame(state).player_counts[0];
    const remove = removable ? h("button", { class: "small", title: "Remove this player", onclick: () => { state.seats.splice(index, 1); rerender(); } }, "Remove") : null;
    const settings = h(
      "details",
      { class: "seat-advanced", open: seat.open ? "" : null, ontoggle: (event) => { seat.open = event.target.open; } },
      h("summary", { class: "small" }, "Model settings"),
      h("div", { class: "fields" }, SEAT_FIELDS.map((field) => h("label", { title: field.hint || "" }, h("span", {}, field.label), seatInput(state, field, seat, changed, rerender), field.hint && field.kind !== "textarea" ? h("small", { class: "muted" }, field.hint) : null))),
    );
    return h(
      "div",
      { class: "panel seat-card" },
      h("div", { class: "seat-head" }, h("span", { class: "seat" }, h("span", { class: `dot p${index}` }), h("strong", {}, `Player ${index + 1}`)), remove),
      h("label", { class: "model-field" }, h("span", {}, "Model"), modelPicker(state, seat, changed, rerender)),
      settings,
    );
  }

  function gameCard(state, game, rerender) {
    const chosen = game.id === state.game;
    return h(
      "button",
      { class: `game-card${chosen ? " chosen" : ""}`, type: "button", onclick: () => { state.game = game.id; state.settings = {}; fitSeats(state); rerender(); } },
      h("strong", {}, game.name),
      h("span", { class: "muted small" }, game.summary),
      h("span", { class: "small" }, playerRange(game.player_counts)),
    );
  }

  function optionInput(state, game, key, defaultValue, changed) {
    const meta = GAME_OPTIONS[`${game.id}.${key}`] || { label: humanize(key) };
    let input;
    if (typeof defaultValue === "boolean") {
      input = h("input", { type: "checkbox", onchange: (event) => { state.settings[key] = event.target.checked; changed(); } });
      input.checked = state.settings[key] === undefined ? defaultValue : state.settings[key];
    } else {
      const numeric = typeof defaultValue === "number" || defaultValue === null;
      input = h("input", {
        type: numeric ? "number" : "text",
        min: meta.min,
        max: meta.max,
        placeholder: defaultValue === null ? "none" : `default: ${defaultValue}`,
        oninput: (event) => {
          const raw = event.target.value;
          state.settings[key] = raw === "" ? undefined : numeric ? Number(raw) : raw;
          changed();
        },
      });
      input.value = state.settings[key] === undefined ? "" : String(state.settings[key]);
    }
    return h("label", {}, h("span", {}, meta.label), input, meta.hint ? h("small", { class: "muted" }, meta.hint) : null);
  }

  function sameModelControl(state, rerender) {
    const select = h("select", { onchange: (event) => {
      if (!event.target.value) return;
      for (const seat of state.seats) {
        seat.model = event.target.value;
        seat.custom = false;
      }
      rerender();
    } }, h("option", { value: "" }, "Give everyone the same model…"), state.options.models.map((id) => h("option", { value: id }, modelName(id))));
    return select;
  }

  function summaryText(state) {
    const models = [...new Set(state.seats.map((seat) => seat.model.trim() || state.options.default_model))];
    const who = models.length === 1 ? `all playing ${modelName(models[0])}` : `${models.length} different models`;
    return `${currentGame(state).name} with ${state.seats.length} players, ${who}.`;
  }

  function renderForm(state, launches) {
    const rerender = () => renderForm(state, launches);
    const game = currentGame(state);
    const counts = game.player_counts;
    const summary = h("p", { class: "start-summary" });
    const preview = h("pre", { class: "config-preview" });
    const changed = () => {
      summary.textContent = summaryText(state);
      preview.textContent = JSON.stringify(matchConfig(state, state.seed === "" ? "(random)" : Number(state.seed)), null, 2);
    };
    const options = Object.entries(game.settings).map(([key, value]) => optionInput(state, game, key, value, changed));
    const full = state.seats.length >= counts[counts.length - 1];
    const add = h("button", { type: "button", disabled: full ? "" : null, title: full ? `${game.name} seats at most ${counts[counts.length - 1]} players` : "", onclick: () => { state.seats.push(newSeat(state)); rerender(); } }, "+ Add player");
    const seed = h("input", { type: "number", value: state.seed, placeholder: "random each time", oninput: (event) => { state.seed = event.target.value; changed(); } });
    const message = h("p", { class: "error" });
    const start = h("button", { class: "primary big", type: "button", onclick: async () => {
      message.textContent = "";
      start.disabled = true;
      const seedValue = state.seed === "" ? Math.floor(Math.random() * 1000000) : Number(state.seed);
      try {
        const launch = await send("/api/matches", { yaml: JSON.stringify(matchConfig(state, seedValue), null, 2) });
        location.hash = `#/match/${launch.match_id}`;
      } catch (error) {
        message.textContent = error.message;
        start.disabled = false;
      }
    } }, "Start match");
    changed();
    app.replaceChildren(h(
      "section",
      { class: "new-match" },
      h("h1", {}, "New match"),
      h("p", { class: "muted" }, "Choose a game, then who plays it. Every player is a language model through OpenRouter."),
      h("h2", {}, "1. Game"),
      h("div", { class: "game-picker" }, state.options.games.map((g) => gameCard(state, g, rerender))),
      options.length ? h("div", { class: "panel fields game-options" }, options) : null,
      h("div", { class: "seats-head" }, h("h2", {}, `2. Players `, h("span", { class: "muted small" }, `${state.seats.length} (${playerRange(counts).replace(" players", "")} allowed)`)), add, sameModelControl(state, rerender)),
      h("div", { class: "seat-grid" }, state.seats.map((seat, index) => seatCard(state, seat, index, changed, rerender))),
      h("h2", {}, "3. Start"),
      h("div", { class: "panel start-panel" },
        summary,
        start,
        message,
        h("details", { class: "more-options" },
          h("summary", { class: "small" }, "More options"),
          h("div", { class: "fields" }, h("label", {}, h("span", {}, "Seed"), seed, h("small", { class: "muted" }, "The same seed deals the same board; leave empty for a new one."))),
          h("p", { class: "muted small" }, "Config sent to the server:"),
          preview)),
      launches.length ? h("div", {}, h("h2", {}, "Started from here"), h("ul", {}, launches.map(launchRow))) : null,
    ));
  }

  async function renderNew() {
    setActiveNav("new");
    const [options, launches] = await Promise.all([api("/api/match-options"), api("/api/launches")]);
    const state = { options, game: options.games[0].id, settings: {}, seed: "", seats: [] };
    fitSeats(state);
    renderForm(state, launches);
  }

  routes.new = renderNew;
})();
