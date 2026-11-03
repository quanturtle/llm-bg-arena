// New match page: pick a game, its settings and one model per seat, then start the match.
(function () {
  const { h, api, send, setActiveNav, routes, app } = window.viewer;

  // Optional settings per seat; an empty field keeps the server's default.
  const SEAT_FIELDS = [
    { key: "label", label: "Label", kind: "text", hint: "shown next to the model id" },
    { key: "temperature", label: "Temperature", kind: "number", step: "0.1", min: "0", max: "2" },
    { key: "top_p", label: "Top p", kind: "number", step: "0.05", min: "0", max: "1" },
    { key: "max_tokens", label: "Max tokens", kind: "number", step: "1", min: "1" },
    { key: "reasoning_effort", label: "Reasoning effort", kind: "select", options: ["low", "medium", "high"] },
    { key: "thinking_budget_tokens", label: "Thinking budget (tokens)", kind: "number", step: "1", min: "1" },
    { key: "output_mode", label: "Answer mode", kind: "select", options: ["tool", "text", "tools"] },
    { key: "max_tool_calls", label: "Max tool calls (tools mode)", kind: "number", step: "1", min: "1" },
    { key: "max_illegal_retries", label: "Retries after an illegal move", kind: "number", step: "1", min: "0" },
    { key: "fallback", label: "When retries run out", kind: "select", options: ["random", "default", "forfeit"] },
    { key: "timeout_seconds", label: "Timeout per call (s)", kind: "number", step: "1", min: "1" },
    { key: "persona", label: "Persona", kind: "textarea", hint: "extra instructions for this player" },
  ];

  function launchRow(launch) {
    const link = h("a", { href: `#/match/${launch.match_id}` }, launch.match_id);
    const badge = h("span", { class: `badge ${launch.status}` }, launch.status);
    return h("li", {}, link, " ", badge, launch.error ? h("span", { class: "error" }, ` ${launch.error}`) : null);
  }

  function newSeat(model) {
    return { model, settings: {} };
  }

  function randomSeed() {
    return Math.floor(Math.random() * 1000000);
  }

  // A number field's value, or undefined when empty, so the default applies.
  function fieldValue(field, raw) {
    if (raw === "" || raw === undefined || raw === null) return undefined;
    return field.kind === "number" ? Number(raw) : raw;
  }

  // The match config the server receives: only settings the user filled in.
  function matchConfig(state) {
    const config = { num_players: state.seats.length };
    for (const [key, value] of Object.entries(state.settings)) {
      if (value !== undefined) config[key] = value;
    }
    const seats = state.seats.map((seat) => {
      const entry = { agent: "llm", model: seat.model.trim() || state.options.default_model };
      for (const [key, value] of Object.entries(seat.settings)) {
        if (value !== undefined) entry[key] = value;
      }
      return entry;
    });
    return { game: state.game, config, seed: state.seed, seats };
  }

  function seatInput(field, seat, onChange) {
    const current = seat.settings[field.key];
    const update = (raw) => {
      seat.settings[field.key] = fieldValue(field, raw);
      onChange();
    };
    if (field.kind === "select") {
      const select = h("select", { onchange: (event) => update(event.target.value) }, h("option", { value: "" }, "default"), field.options.map((option) => h("option", { value: option }, option)));
      select.value = current === undefined ? "" : String(current);
      return select;
    }
    if (field.kind === "textarea") {
      const area = h("textarea", { rows: 2, placeholder: field.hint || "", oninput: (event) => update(event.target.value) });
      area.value = current === undefined ? "" : current;
      return area;
    }
    const input = h("input", { type: field.kind, step: field.step, min: field.min, max: field.max, placeholder: field.hint || "default", oninput: (event) => update(event.target.value) });
    input.value = current === undefined ? "" : String(current);
    return input;
  }

  function seatCard(state, seat, index, rerender, refreshPreview) {
    const counts = state.game ? currentGame(state).player_counts : [];
    const removable = state.seats.length > counts[0];
    const model = h("input", { type: "text", list: "model-list", value: seat.model, placeholder: state.options.default_model, oninput: (event) => { seat.model = event.target.value; refreshPreview(); } });
    const advanced = h(
      "details",
      { class: "seat-advanced" },
      h("summary", { class: "muted small" }, "Model settings"),
      h("div", { class: "fields" }, SEAT_FIELDS.map((field) => h("label", {}, h("span", {}, field.label), seatInput(field, seat, refreshPreview)))),
    );
    return h(
      "div",
      { class: "panel seat-card" },
      h("div", { class: "seat-head" }, h("span", { class: "seat" }, h("span", { class: `dot p${index}` }), h("strong", {}, `P${index + 1}`)), removable ? h("button", { class: "small", onclick: () => { state.seats.splice(index, 1); rerender(); } }, "Remove") : null),
      h("label", { class: "model-field" }, h("span", {}, "Model"), model),
      advanced,
    );
  }

  function settingInput(state, key, defaultValue, refreshPreview) {
    if (typeof defaultValue === "boolean") {
      const box = h("input", { type: "checkbox", onchange: (event) => { state.settings[key] = event.target.checked; refreshPreview(); } });
      box.checked = state.settings[key] === undefined ? defaultValue : state.settings[key];
      return box;
    }
    const numeric = typeof defaultValue === "number" || defaultValue === null;
    const input = h("input", {
      type: numeric ? "number" : "text",
      placeholder: defaultValue === null ? "none" : String(defaultValue),
      oninput: (event) => {
        const raw = event.target.value;
        state.settings[key] = raw === "" ? undefined : numeric ? Number(raw) : raw;
        refreshPreview();
      },
    });
    input.value = state.settings[key] === undefined ? "" : String(state.settings[key]);
    return input;
  }

  function currentGame(state) {
    return state.options.games.find((game) => game.id === state.game);
  }

  // Keep the seats already set up, then trim or pad to the game's smallest valid count.
  function fitSeats(state) {
    const counts = currentGame(state).player_counts;
    const target = Math.min(Math.max(state.seats.length, counts[0]), counts[counts.length - 1]);
    state.seats = state.seats.slice(0, target);
    while (state.seats.length < counts[0]) state.seats.push(newSeat(state.options.default_model));
  }

  function renderForm(state, launches) {
    const rerender = () => renderForm(state, launches);
    const preview = h("pre", { class: "config-preview" });
    const refreshPreview = () => { preview.textContent = JSON.stringify(matchConfig(state), null, 2); };
    const game = currentGame(state);
    const counts = game.player_counts;
    const gameSelect = h("select", { onchange: (event) => { state.game = event.target.value; state.settings = {}; fitSeats(state); rerender(); } }, state.options.games.map((g) => h("option", { value: g.id }, g.id)));
    gameSelect.value = state.game;
    const seed = h("input", { type: "number", value: state.seed, oninput: (event) => { state.seed = Number(event.target.value) || 0; refreshPreview(); } });
    const settings = Object.entries(game.settings).map(([key, value]) => h("label", {}, h("span", {}, key), settingInput(state, key, value, refreshPreview)));
    const canAdd = state.seats.length < counts[counts.length - 1];
    const add = h("button", { onclick: () => { state.seats.push(newSeat(state.options.default_model)); rerender(); }, disabled: canAdd ? null : "" }, "Add player");
    const message = h("p", { class: "error" });
    const start = h("button", { class: "primary", onclick: async () => {
      message.textContent = "";
      start.disabled = true;
      try {
        const launch = await send("/api/matches", { yaml: JSON.stringify(matchConfig(state), null, 2) });
        location.hash = `#/match/${launch.match_id}`;
      } catch (error) {
        message.textContent = error.message;
        start.disabled = false;
      }
    } }, "Start match");
    refreshPreview();
    app.replaceChildren(h(
      "section",
      { class: "new-match" },
      h("h1", {}, "New match"),
      h("datalist", { id: "model-list" }, state.options.models.map((model) => h("option", { value: model }))),
      h("div", { class: "panel stack" },
        h("div", { class: "fields" },
          h("label", {}, h("span", {}, "Game"), gameSelect),
          h("label", {}, h("span", {}, "Seed"), seed),
          settings),
      ),
      h("div", { class: "seats-head" }, h("h2", {}, `Players (${state.seats.length}; ${counts[0] === counts[counts.length - 1] ? counts[0] : `${counts[0]} to ${counts[counts.length - 1]}`} allowed)`), add),
      h("div", { class: "seat-grid" }, state.seats.map((seat, index) => seatCard(state, seat, index, rerender, refreshPreview))),
      h("p", { class: "muted small" }, `Every seat is a language model through OpenRouter; an empty model field uses ${state.options.default_model}, and empty settings keep the defaults.`),
      h("div", { class: "toolbar" }, start),
      message,
      h("details", {}, h("summary", { class: "muted small" }, "Config sent to the server"), preview),
      launches.length ? h("div", {}, h("h2", {}, "Started from here"), h("ul", {}, launches.map(launchRow))) : null,
    ));
  }

  async function renderNew() {
    setActiveNav("new");
    const [options, launches] = await Promise.all([api("/api/match-options"), api("/api/launches")]);
    const state = { options, game: options.games[0].id, settings: {}, seed: randomSeed(), seats: [] };
    fitSeats(state);
    renderForm(state, launches);
  }

  routes.new = renderNew;
})();
