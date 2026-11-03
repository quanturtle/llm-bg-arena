// Single-page viewer: hash routes over the JSON API in boardgames/web/app.py.
(function () {
  const app = document.getElementById("app");
  const layouts = {};
  let games = null;

  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "style") node.style.cssText = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  async function api(path) {
    const response = await fetch(path);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        message = (await response.json()).error || message;
      } catch (error) {
        // the body was not JSON; keep the status text
      }
      throw new Error(message);
    }
    return response.json();
  }

  async function loadGames() {
    if (!games) games = await api("/api/games");
    return games;
  }

  async function loadLayout(gameId) {
    if (!(gameId in layouts)) {
      try {
        layouts[gameId] = await api(`/api/games/${gameId}/layout`);
      } catch (error) {
        layouts[gameId] = null;
      }
    }
    return layouts[gameId];
  }

  function formatCost(cost) {
    if (cost === null || cost === undefined) return "n/a";
    if (cost === 0) return "$0";
    return cost < 0.01 ? `$${cost.toFixed(4)}` : `$${cost.toFixed(2)}`;
  }

  function formatDate(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
  }

  function formatSeconds(seconds) {
    return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(1)} s`;
  }

  function seatChip(match, player, extra) {
    const seat = match.seats[player];
    return h("span", { class: "seat" }, h("span", { class: `dot p${player}` }), `P${player + 1} `, h("a", { href: `#/agent/${encodeURIComponent(seat.agent)}` }, seat.agent), extra);
  }

  function statusBadge(match) {
    return h("span", { class: `badge ${match.status}` }, match.status);
  }

  function matchCost(match) {
    let total = 0;
    for (const seat of match.seats) {
      if (seat.cost_usd === null) return null;
      total += seat.cost_usd;
    }
    return total;
  }

  function setActiveNav(route) {
    for (const link of document.querySelectorAll(".topbar nav a")) {
      link.classList.toggle("active", link.dataset.route === route);
    }
  }

  function showError(error) {
    app.replaceChildren(h("div", { class: "panel" }, h("p", { class: "error" }, error.message)));
  }

  // --- matches page -------------------------------------------------------

  function matchRow(match) {
    const winners = new Set(match.winners || match.seats.filter((s) => s.rank === 1).map((s) => s.player));
    const seats = match.seats.map((seat) => {
      const badge = winners.has(seat.player) && match.status === "finished" ? h("span", { class: "badge winner" }, "win") : seat.forfeited ? h("span", { class: "badge forfeit" }, "forfeit") : null;
      return seatChip(match, seat.player, badge ? [" ", badge] : null);
    });
    const row = h(
      "tr",
      { class: "link", onclick: () => { location.hash = `#/match/${match.match_id}`; } },
      h("td", { class: "small muted" }, formatDate(match.started_at)),
      h("td", {}, h("a", { href: `#/games/${match.game_id}` }, match.game_id), " ", h("span", { class: "muted small mono" }, `seed ${match.seed}`)),
      h("td", {}, h("div", { class: "seat-list" }, seats)),
      h("td", { class: "num" }, match.steps),
      h("td", { class: "num" }, formatCost(matchCost(match))),
      h("td", {}, statusBadge(match)),
    );
    return row;
  }

  async function renderMatches(params) {
    setActiveNav("matches");
    const query = new URLSearchParams();
    if (params.get("game")) query.set("game", params.get("game"));
    if (params.get("agent")) query.set("agent", params.get("agent"));
    const [catalog, gameList] = await Promise.all([api(`/api/matches?${query}`), loadGames()]);
    const gameSelect = h("select", { onchange: (event) => navigateMatches({ game: event.target.value, agent: params.get("agent") }) }, h("option", { value: "" }, "All games"), gameList.map((g) => h("option", { value: g.id, selected: g.id === params.get("game") ? "" : null }, `${g.id} (${g.matches})`)));
    if (!params.get("game")) gameSelect.value = "";
    const agentInput = h("input", { type: "text", placeholder: "agent name", value: params.get("agent") || "" });
    agentInput.addEventListener("change", () => navigateMatches({ game: params.get("game"), agent: agentInput.value }));
    const toolbar = h("div", { class: "toolbar" }, h("label", {}, "Game ", gameSelect), h("label", {}, "Agent ", agentInput), h("span", { class: "muted small" }, `${catalog.matches.length} matches`));
    const table = h(
      "table",
      {},
      h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "Game"), h("th", {}, "Seats"), h("th", { class: "num" }, "Steps"), h("th", { class: "num" }, "Cost"), h("th", {}, "Status"))),
      h("tbody", {}, catalog.matches.map(matchRow)),
    );
    const empty = catalog.matches.length ? null : h("p", { class: "muted" }, "No matches yet. Play one with `arena play` and it appears here.");
    const unreadable = catalog.unreadable.length ? h("p", { class: "small error" }, `${catalog.unreadable.length} log file(s) could not be read: `, catalog.unreadable.map((u) => `${u.path}`).join(", ")) : null;
    app.replaceChildren(h("h1", {}, "Matches"), toolbar, h("div", { class: "panel" }, table, empty), unreadable);
  }

  function navigateMatches(filters) {
    const query = new URLSearchParams();
    if (filters.game) query.set("game", filters.game);
    if (filters.agent) query.set("agent", filters.agent);
    const suffix = query.toString();
    location.hash = `#/matches${suffix ? `?${suffix}` : ""}`;
  }

  // --- match page ---------------------------------------------------------

  const SPEEDS = [0.5, 1, 2, 4];

  function pointsChart(outline, step, onSeek) {
    const width = 600;
    const height = 120;
    const pad = 6;
    const frames = outline.scores.length;
    const players = outline.match.seats.length;
    let max = 1;
    for (const scores of outline.scores) for (const s of scores) max = Math.max(max, s.points);
    const x = (i) => pad + (frames <= 1 ? 0 : (i / (frames - 1)) * (width - 2 * pad));
    const y = (p) => height - pad - (p / max) * (height - 2 * pad);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("class", "chart");
    svg.setAttribute("preserveAspectRatio", "none");
    for (let player = 0; player < players; player += 1) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      line.setAttribute("points", outline.scores.map((scores, i) => `${x(i)},${y(scores[player].points)}`).join(" "));
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", `var(--p${player + 1})`);
      line.setAttribute("stroke-width", "2");
      line.setAttribute("vector-effect", "non-scaling-stroke");
      svg.append(line);
    }
    const cursor = document.createElementNS("http://www.w3.org/2000/svg", "line");
    cursor.setAttribute("x1", x(step));
    cursor.setAttribute("x2", x(step));
    cursor.setAttribute("y1", 0);
    cursor.setAttribute("y2", height);
    cursor.setAttribute("stroke", "var(--muted)");
    cursor.setAttribute("stroke-dasharray", "3 3");
    cursor.setAttribute("vector-effect", "non-scaling-stroke");
    svg.append(cursor);
    svg.addEventListener("click", (event) => {
      const box = svg.getBoundingClientRect();
      const ratio = (event.clientX - box.left) / box.width;
      onSeek(Math.round(Math.min(1, Math.max(0, ratio)) * (frames - 1)));
    });
    return h("div", {}, h("h3", {}, `Points (max ${max})`), svg);
  }

  function visibleEvents(outline, step, viewer, omniscient) {
    return outline.events.filter((event) => {
      if (event.step > step) return false;
      if (omniscient || event.audience === "everyone") return true;
      return viewer !== null && event.audience.includes(viewer);
    });
  }

  function eventList(outline, step, viewer, omniscient) {
    const items = visibleEvents(outline, step, viewer, omniscient).map((event) => {
      const isPrivate = event.audience !== "everyone";
      const classes = [];
      if (event.step === step) classes.push("current");
      if (isPrivate) classes.push("private");
      const who = isPrivate ? ` (seen by ${event.audience.map((p) => `P${p + 1}`).join(", ")})` : "";
      return h("li", { class: classes.join(" ") }, h("span", { class: "step" }, event.step), event.text, who);
    });
    const list = h("ul", { class: "events" }, items);
    requestAnimationFrame(() => {
      const current = list.querySelector(".current");
      if (current) current.scrollIntoView({ block: "nearest" });
    });
    return list;
  }

  function attemptList(trace) {
    const rejected = trace.attempts.filter((a) => a.rejection);
    if (!rejected.length) return null;
    return h("div", {}, h("h3", {}, `${rejected.length} rejected attempt(s)`), rejected.map((attempt) => h("div", { class: "attempt small" }, attempt.answer !== undefined ? h("div", { class: "mono" }, String(attempt.answer)) : null, h("div", { class: "muted" }, `${attempt.rejection.kind}: ${attempt.rejection.feedback || ""}`))));
  }

  function decisionPanel(match, frame) {
    if (!frame.decision && !frame.forfeits.length) {
      return h("div", { class: "panel decision" }, h("h2", {}, "Setup"), h("p", { class: "muted" }, frame.pending.length ? `Waiting for ${frame.pending.map((p) => `P${p + 1}`).join(", ")}.` : "No decision yet."));
    }
    const parts = [];
    if (frame.decision) {
      const d = frame.decision;
      const trace = d.trace;
      const usage = trace.prompt_tokens + trace.completion_tokens;
      parts.push(
        h("h2", {}, seatChip(match, d.player), " ", h("code", {}, d.action)),
        h("dl", {}, h("dt", {}, "Did"), h("dd", {}, d.description), h("dt", {}, "Asked"), h("dd", { class: "muted" }, d.prompt), h("dt", {}, "Took"), h("dd", {}, formatSeconds(d.latency_seconds), usage ? `, ${usage} tokens, ${formatCost(trace.cost_usd)}` : ""), trace.fallback ? h("dt", {}, "Fallback") : null, trace.fallback ? h("dd", { class: "error" }, trace.fallback) : null),
        trace.reasoning ? h("div", {}, h("h3", {}, "Reasoning"), h("pre", { class: "reasoning" }, trace.reasoning)) : null,
        trace.memory ? h("div", {}, h("h3", {}, "Notes kept"), h("pre", { class: "reasoning" }, trace.memory)) : null,
        attemptList(trace),
      );
    }
    for (const forfeit of frame.forfeits) {
      parts.push(h("h2", {}, seatChip(match, forfeit.player), " ", h("span", { class: "badge forfeit" }, "forfeits")), h("p", {}, forfeit.reason), forfeit.trace.reasoning ? h("pre", { class: "reasoning" }, forfeit.trace.reasoning) : null, attemptList(forfeit.trace));
    }
    return h("div", { class: "panel decision stack" }, parts);
  }

  function scoreRow(match, frame) {
    return h("div", { class: "scores" }, frame.scores.map((score) => seatChip(match, score.player, [": ", h("strong", {}, score.points), match.status === "finished" && frame.step === match.steps ? ` (#${score.rank})` : ""])));
  }

  function boardPanel(match, frame, viewer, layout) {
    const board = frame.boards.find((b) => b.viewer === viewer) || frame.boards[0];
    const renderer = window.boards[match.game_id];
    let content = null;
    if (viewer === null && renderer && board.observation) {
      try {
        content = renderer(board.observation, { layout, frame, match, lastEvents: frame.events });
      } catch (error) {
        console.error("board renderer failed", error);
        content = null;
      }
    }
    const text = h("details", { open: content ? null : "" }, h("summary", { class: "muted small" }, "Text view"), h("pre", {}, board.text));
    return h("div", { class: "panel board stack" }, content, text, scoreRow(match, frame));
  }

  function matchHeader(match) {
    const config = Object.entries(match.config).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ");
    return h(
      "div",
      { class: "match-head" },
      h("div", {}, h("h1", {}, h("a", { href: `#/games/${match.game_id}` }, match.game_id), " ", h("span", { class: "muted mono small" }, match.match_id), " ", statusBadge(match)), h("div", { class: "muted small mono" }, `seed ${match.seed} · ${config}`)),
      h("div", { class: "seat-list" }, match.seats.map((seat) => seatChip(match, seat.player, seat.rank === 1 && match.status === "finished" ? [" ", h("span", { class: "badge winner" }, "winner")] : seat.forfeited ? [" ", h("span", { class: "badge forfeit" }, "forfeit")] : null))),
    );
  }

  function matchPage(matchId, params) {
    const frames = new Map();
    let outline = null;
    let layout = null;
    let step = Number(params.get("step") || 0);
    let viewer = params.get("viewer") === null || params.get("viewer") === "" ? null : Number(params.get("viewer"));
    let omniscient = params.get("all") === "1";
    let playing = false;
    let speed = 1;
    let timer = null;
    let poll = null;
    let disposed = false;

    const frameOf = async (n) => {
      if (!frames.has(n)) frames.set(n, api(`/api/matches/${matchId}/frames/${n}`));
      return frames.get(n);
    };

    const last = () => outline.frame_count - 1;

    const seek = (n) => {
      step = Math.min(last(), Math.max(0, n));
      if (step === last() && outline.match.status === "finished") stop();
      render();
    };

    const stop = () => {
      playing = false;
      if (timer) clearInterval(timer);
      timer = null;
    };

    const play = () => {
      if (playing) return stop();
      playing = true;
      timer = setInterval(() => {
        if (step >= last()) {
          if (outline.match.status === "finished") stop();
          return;
        }
        seek(step + 1);
      }, 1200 / speed);
      render();
    };

    const onKey = (event) => {
      if (event.target.tagName === "INPUT" || event.target.tagName === "SELECT") return;
      if (event.key === "ArrowLeft") seek(step - 1);
      else if (event.key === "ArrowRight") seek(step + 1);
      else if (event.key === "Home") seek(0);
      else if (event.key === "End") seek(last());
      else if (event.key === " ") { event.preventDefault(); play(); }
    };

    const refreshOutline = async () => {
      const fresh = await api(`/api/matches/${matchId}/timeline`);
      const grew = outline && fresh.frame_count > outline.frame_count;
      const wasAtEnd = outline && step === last();
      outline = fresh;
      if (grew && wasAtEnd) step = last();
      if (fresh.match.status === "finished" && poll) {
        clearInterval(poll);
        poll = null;
      }
      if (grew) render();
    };

    const controls = () => {
      const slider = h("input", { type: "range", min: 0, max: last(), value: step });
      slider.addEventListener("input", (event) => seek(Number(event.target.value)));
      const viewerSelect = h("select", {}, h("option", { value: "" }, "Spectator"), outline.match.seats.map((seat) => h("option", { value: seat.player }, `P${seat.player + 1} ${seat.agent}`)));
      viewerSelect.value = viewer === null ? "" : String(viewer);
      viewerSelect.addEventListener("change", () => { viewer = viewerSelect.value === "" ? null : Number(viewerSelect.value); render(); });
      const speedSelect = h("select", {}, SPEEDS.map((s) => h("option", { value: s }, `${s}×`)));
      speedSelect.value = String(speed);
      speedSelect.addEventListener("change", () => { speed = Number(speedSelect.value); if (playing) { stop(); play(); } });
      const allEvents = h("input", { type: "checkbox" });
      allEvents.checked = omniscient;
      allEvents.addEventListener("change", () => { omniscient = allEvents.checked; render(); });
      return h(
        "div",
        { class: "controls" },
        h("button", { onclick: () => seek(0), title: "first (Home)" }, "⏮"),
        h("button", { onclick: () => seek(step - 1), title: "previous (←)" }, "◀"),
        h("button", { class: playing ? "primary" : "", onclick: play, title: "play/pause (space)" }, playing ? "⏸" : "▶"),
        h("button", { onclick: () => seek(step + 1), title: "next (→)" }, "▶|"),
        h("button", { onclick: () => seek(last()), title: "last (End)" }, "⏭"),
        speedSelect,
        slider,
        h("span", { class: "step mono" }, `step ${step} / ${last()}`),
        h("label", {}, "View ", viewerSelect),
        h("label", {}, allEvents, " all events"),
      );
    };

    const render = async () => {
      if (disposed) return;
      const current = step;
      const query = new URLSearchParams();
      if (step) query.set("step", step);
      if (viewer !== null) query.set("viewer", viewer);
      if (omniscient) query.set("all", "1");
      history.replaceState(null, "", `#/match/${matchId}${query.toString() ? `?${query}` : ""}`);
      let frame;
      try {
        frame = await frameOf(current);
      } catch (error) {
        return showError(error);
      }
      if (disposed || current !== step) return;
      if (current < last()) frameOf(current + 1);
      const match = outline.match;
      app.replaceChildren(
        matchHeader(match),
        controls(),
        h(
          "div",
          { class: "match-grid" },
          h("div", { class: "stack" }, boardPanel(match, frame, viewer, layout), h("div", { class: "panel" }, pointsChart(outline, step, seek))),
          h("div", { class: "stack" }, decisionPanel(match, frame), h("div", { class: "panel" }, h("h3", {}, "Events"), eventList(outline, step, viewer, omniscient))),
        ),
      );
    };

    const start = async () => {
      setActiveNav("matches");
      try {
        await refreshOutline();
        layout = await loadLayout(outline.match.game_id);
      } catch (error) {
        return showError(error);
      }
      if (!params.has("step") && outline.match.status === "running") step = last();
      step = Math.min(last(), Math.max(0, step));
      if (outline.match.status === "running") poll = setInterval(refreshOutline, 2000);
      document.addEventListener("keydown", onKey);
      render();
    };

    const dispose = () => {
      disposed = true;
      stop();
      if (poll) clearInterval(poll);
      document.removeEventListener("keydown", onKey);
    };

    return { start, dispose };
  }

  // --- router -------------------------------------------------------------

  let current = null;
  const routes = {
    matches: (_, params) => renderMatches(params),
  };
  window.viewerRoutes = routes;

  function parseHash() {
    const hash = location.hash.replace(/^#\/?/, "") || "matches";
    const [path, query = ""] = hash.split("?");
    const [name, ...rest] = path.split("/");
    return { name, args: rest.map(decodeURIComponent), params: new URLSearchParams(query) };
  }

  async function route() {
    const { name, args, params } = parseHash();
    const id = name === "match" ? location.hash.split("?")[0] : location.hash;
    if (current && current.id === id) return;
    if (current && current.dispose) current.dispose();
    current = { id };
    try {
      if (name === "match" && args[0]) {
        const page = matchPage(args[0], params);
        current.dispose = page.dispose;
        await page.start();
      } else if (routes[name]) {
        await routes[name](args, params);
      } else {
        app.replaceChildren(h("div", { class: "panel" }, h("p", { class: "error" }, `Unknown page: ${name}`)));
      }
    } catch (error) {
      showError(error);
    }
  }

  window.addEventListener("hashchange", route);
  route();
})();
