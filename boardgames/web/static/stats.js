// Leaderboard and agent pages, added to the viewer's routes.
(function () {
  const { h, api, loadGames, formatCost, formatSeconds, seatChip, matchRow, setActiveNav, routes, app } = window.viewer;

  function percent(value) {
    return `${Math.round(value * 100)}%`;
  }

  function agentLink(name) {
    return h("a", { href: `#/agent/${encodeURIComponent(name)}` }, name);
  }

  // The models an agent name played with, when the name is a label rather than a model id.
  function modelNote(row) {
    const models = (row.models || []).filter((model) => model !== row.agent);
    return models.length ? h("span", { class: "muted small" }, ` ${models.join(", ")}`) : null;
  }

  // Version 0 is the logs recorded before prompts were versioned.
  function promptText(version) {
    return version ? `prompt v${version}` : "unversioned prompt";
  }

  function statsHeader(withElo, withGame, withPrompt) {
    return h(
      "tr",
      {},
      h("th", {}, "#"),
      h("th", {}, "Agent"),
      withGame ? h("th", {}, "Game") : null,
      withPrompt ? h("th", {}, "Prompt") : null,
      withElo ? h("th", { class: "num" }, "Elo") : null,
      h("th", { class: "num" }, "Matches"),
      h("th", { class: "num" }, "Wins"),
      h("th", { class: "num" }, "Win rate"),
      h("th", { class: "num" }, "Avg rank"),
      h("th", { class: "num" }, "Avg points"),
      h("th", { class: "num" }, "Forfeits"),
      h("th", { class: "num" }, "Illegal"),
      h("th", { class: "num" }, "Fallbacks"),
      h("th", { class: "num" }, "Latency"),
      h("th", { class: "num" }, "Tokens"),
      h("th", { class: "num" }, "Cost / match"),
    );
  }

  function statsRow(row, index, withElo, withGame, withPrompt) {
    return h(
      "tr",
      {},
      h("td", { class: "muted" }, index + 1),
      h("td", {}, agentLink(row.agent), " ", h("span", { class: "badge" }, row.kind), modelNote(row)),
      withGame ? h("td", {}, h("a", { href: `#/games/${row.game_id}` }, row.game_id)) : null,
      withPrompt ? h("td", {}, promptText(row.prompt_version)) : null,
      withElo ? h("td", { class: "num" }, h("strong", {}, Math.round(row.elo))) : null,
      h("td", { class: "num" }, row.matches),
      h("td", { class: "num" }, row.wins),
      h("td", { class: "num" }, percent(row.win_rate)),
      h("td", { class: "num" }, row.average_rank.toFixed(2)),
      h("td", { class: "num" }, row.average_points.toFixed(1)),
      h("td", { class: "num" }, row.forfeits),
      h("td", { class: "num", title: `${row.illegal_attempts} rejected answers over ${row.decisions} decisions` }, percent(row.illegal_rate)),
      h("td", { class: "num" }, row.fallbacks),
      h("td", { class: "num" }, formatSeconds(row.average_latency_seconds)),
      h("td", { class: "num" }, row.prompt_tokens + row.completion_tokens),
      h("td", { class: "num" }, formatCost(row.cost_per_match)),
    );
  }

  function statsTable(rows, withElo, withGame, withPrompt = false) {
    return h("div", { class: "panel", style: "overflow: auto" }, h("table", {}, h("thead", {}, statsHeader(withElo, withGame, withPrompt)), h("tbody", {}, rows.map((row, i) => statsRow(row, i, withElo, withGame, withPrompt)))));
  }

  function leaderboardHash(game, prompt) {
    const query = new URLSearchParams();
    if (game) query.set("game", game);
    if (prompt !== "") query.set("prompt", prompt);
    return query.toString() ? `#/leaderboard?${query}` : "#/leaderboard";
  }

  async function renderLeaderboard(_, params) {
    setActiveNav("leaderboard");
    const game = params.get("game") || "";
    const prompt = params.get("prompt") || "";
    const [board, games] = await Promise.all([api(`/api/leaderboard${leaderboardHash(game, prompt).replace("#/leaderboard", "")}`), loadGames()]);
    const select = h("select", {}, h("option", { value: "" }, "All games"), games.map((g) => h("option", { value: g.id }, g.id)));
    select.value = game;
    select.addEventListener("change", () => { location.hash = leaderboardHash(select.value, prompt); });
    // compare how models play under each revision of the prompt
    const promptSelect = h("select", {}, h("option", { value: "" }, "All prompts"), board.prompt_versions.map((version) => h("option", { value: version }, promptText(version))));
    promptSelect.value = prompt;
    promptSelect.addEventListener("change", () => { location.hash = leaderboardHash(game, promptSelect.value); });
    const note = game
      ? "Elo starts at 1000 with K = 32. In every finished match each pair of seats plays one rated game, ahead or behind by final rank, and a seat's change is the average over its opponents."
      : "Across games there is no shared rating; rows are ordered by win rate, then average rank. Pick a game for Elo.";
    const empty = board.rows.length ? null : h("p", { class: "muted" }, "No finished matches yet.");
    app.replaceChildren(
      h("h1", {}, "Leaderboard"),
      h("div", { class: "toolbar" }, h("label", {}, "Game ", select), h("label", {}, "Prompt ", promptSelect), h("span", { class: "muted small" }, `${board.finished_matches} finished matches`)),
      statsTable(board.rows, Boolean(game), !game),
      empty || "",
      h("p", { class: "muted small" }, note, " Wins count sole first places; illegal is the share of answers rejected before a legal action."),
    );
  }

  function summaryCards(row) {
    const cards = [
      ["Matches", row.matches],
      ["Win rate", percent(row.win_rate)],
      ["Avg rank", row.average_rank.toFixed(2)],
      ["Illegal answers", percent(row.illegal_rate)],
      ["Latency / decision", formatSeconds(row.average_latency_seconds)],
      ["Cost / match", formatCost(row.cost_per_match)],
      ["Total cost", formatCost(row.cost_usd)],
    ];
    return h("div", { class: "cards" }, cards.map(([label, value]) => h("div", { class: "panel card" }, h("div", { class: "muted small" }, label), h("div", { class: "value" }, value))));
  }

  function opponentsTable(opponents) {
    if (!opponents.length) return h("p", { class: "muted" }, "No opponents yet.");
    return h(
      "table",
      {},
      h("thead", {}, h("tr", {}, h("th", {}, "Opponent"), h("th", { class: "num" }, "Matches"), h("th", { class: "num" }, "Ahead"), h("th", { class: "num" }, "Level"), h("th", { class: "num" }, "Behind"))),
      h("tbody", {}, opponents.map((o) => h("tr", {}, h("td", {}, agentLink(o.opponent)), h("td", { class: "num" }, o.matches), h("td", { class: "num" }, o.ahead), h("td", { class: "num" }, o.level), h("td", { class: "num" }, o.behind)))),
    );
  }

  async function renderAgent(args) {
    setActiveNav("leaderboard");
    const name = args[0];
    const [detail, catalog] = await Promise.all([api(`/api/agents/${encodeURIComponent(name)}`), api(`/api/matches?agent=${encodeURIComponent(name)}`)]);
    const recent = h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "Game"), h("th", {}, "Seats"), h("th", { class: "num" }, "Steps"), h("th", { class: "num" }, "Cost"), h("th", {}, "Status"))), h("tbody", {}, catalog.matches.slice(0, 50).map(matchRow)));
    app.replaceChildren(
      h("h1", {}, name, " ", h("span", { class: "badge" }, detail.kind)),
      detail.overall ? summaryCards(detail.overall) : "",
      h("div", { class: "stack" }, h("h2", {}, "By game"), statsTable(detail.games, true, true), h("h2", {}, "By prompt version"), statsTable(detail.prompts, false, false, true), h("h2", {}, "Head to head"), h("div", { class: "panel" }, opponentsTable(detail.opponents)), h("h2", {}, "Matches"), h("div", { class: "panel" }, recent)),
    );
  }

  routes.leaderboard = renderLeaderboard;
  routes.agent = renderAgent;
})();
