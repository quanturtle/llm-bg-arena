// Game pages: the list of games and, per game, its rules, defaults, standings and matches.
(function () {
  const { h, api, loadGames, matchRow, setActiveNav, routes, app } = window.viewer;

  // Inline markdown: code spans, bold and emphasis; everything else is text.
  function inline(text) {
    const parts = [];
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
    let last = 0;
    for (const match of text.matchAll(pattern)) {
      parts.push(text.slice(last, match.index));
      const token = match[0];
      if (token.startsWith("`")) parts.push(h("code", {}, token.slice(1, -1)));
      else if (token.startsWith("**")) parts.push(h("strong", {}, token.slice(2, -2)));
      else parts.push(h("em", {}, token.slice(1, -1)));
      last = match.index + token.length;
    }
    parts.push(text.slice(last));
    return parts;
  }

  function tableBlock(lines) {
    const rows = lines.filter((line) => !/^\|?\s*:?-+/.test(line)).map((line) => line.replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()));
    const [head, ...body] = rows;
    return h("table", {}, h("thead", {}, h("tr", {}, head.map((cell) => h("th", {}, inline(cell))))), h("tbody", {}, body.map((row) => h("tr", {}, row.map((cell) => h("td", {}, inline(cell)))))));
  }

  // Block markdown: headings, fenced code, lists, tables and paragraphs.
  function markdown(text) {
    const out = h("div", { class: "rules" });
    const lines = text.split("\n");
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i += 1; continue; }
      const heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) { out.append(h(`h${Math.min(heading[1].length + 1, 6)}`, {}, inline(heading[2]))); i += 1; continue; }
      if (line.startsWith("```")) {
        const code = [];
        i += 1;
        while (i < lines.length && !lines[i].startsWith("```")) { code.push(lines[i]); i += 1; }
        out.append(h("pre", {}, code.join("\n")));
        i += 1;
        continue;
      }
      if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
        const ordered = /^\s*\d+\./.test(line);
        const list = h(ordered ? "ol" : "ul", {});
        while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
          list.append(h("li", {}, inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""))));
          i += 1;
        }
        out.append(list);
        continue;
      }
      if (line.startsWith("|")) {
        const block = [];
        while (i < lines.length && lines[i].startsWith("|")) { block.push(lines[i]); i += 1; }
        out.append(tableBlock(block));
        continue;
      }
      const paragraph = [];
      while (i < lines.length && lines[i].trim() && !/^(#|```|\||\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) { paragraph.push(lines[i]); i += 1; }
      out.append(h("p", {}, inline(paragraph.join(" "))));
    }
    return out;
  }

  async function renderGameList() {
    setActiveNav("games");
    const games = await loadGames();
    const rows = games.map((game) => h("tr", { class: "link", onclick: () => { location.hash = `#/games/${game.id}`; } }, h("td", {}, h("a", { href: `#/games/${game.id}` }, game.id)), h("td", { class: "mono small" }, JSON.stringify(game.default_config)), h("td", { class: "num" }, game.matches)));
    app.replaceChildren(h("h1", {}, "Games"), h("div", { class: "panel" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Game"), h("th", {}, "Default config"), h("th", { class: "num" }, "Matches"))), h("tbody", {}, rows))));
  }

  function standings(board) {
    if (!board.rows.length) return h("p", { class: "muted" }, "No finished matches yet.");
    return h(
      "table",
      {},
      h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "Agent"), h("th", { class: "num" }, "Elo"), h("th", { class: "num" }, "Matches"), h("th", { class: "num" }, "Win rate"), h("th", { class: "num" }, "Avg rank"))),
      h("tbody", {}, board.rows.map((row, i) => h("tr", {}, h("td", { class: "muted" }, i + 1), h("td", {}, h("a", { href: `#/agent/${encodeURIComponent(row.agent)}` }, row.agent)), h("td", { class: "num" }, Math.round(row.elo)), h("td", { class: "num" }, row.matches), h("td", { class: "num" }, `${Math.round(row.win_rate * 100)}%`), h("td", { class: "num" }, row.average_rank.toFixed(2))))),
    );
  }

  async function renderGame(args) {
    if (!args[0]) return renderGameList();
    setActiveNav("games");
    const id = args[0];
    const [game, board, catalog] = await Promise.all([api(`/api/games/${id}`), api(`/api/leaderboard?game=${encodeURIComponent(id)}`), api(`/api/matches?game=${encodeURIComponent(id)}`)]);
    const config = h("dl", { class: "kv" }, Object.entries(game.default_config).flatMap(([key, value]) => [h("dt", {}, key), h("dd", { class: "mono" }, JSON.stringify(value))]));
    const matches = h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "Game"), h("th", {}, "Seats"), h("th", { class: "num" }, "Steps"), h("th", { class: "num" }, "Cost"), h("th", {}, "Status"))), h("tbody", {}, catalog.matches.slice(0, 50).map(matchRow)));
    app.replaceChildren(
      h("h1", {}, id),
      h("div", { class: "match-grid" },
        h("div", { class: "stack" }, h("div", { class: "panel" }, h("h2", {}, "Rules"), markdown(game.rules))),
        h("div", { class: "stack" },
          h("div", { class: "panel" }, h("h2", {}, "Default config"), config, h("p", { class: "muted small" }, "Change it in a match config on the ", h("a", { href: "#/new" }, "New match"), " page.")),
          h("div", { class: "panel" }, h("h2", {}, "Standings"), standings(board), h("p", { class: "small" }, h("a", { href: `#/leaderboard?game=${id}` }, "Full leaderboard"))),
          h("div", { class: "panel" }, h("h2", {}, `Matches (${catalog.matches.length})`), catalog.matches.length ? matches : h("p", { class: "muted" }, "None yet.")),
        ),
      ),
    );
  }

  routes.games = renderGame;
})();
