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

  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        message = (await response.json()).error || message;
      } catch (error) {
        // the body was not JSON; keep the status text
      }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    return response.json();
  }

  // DELETE a resource; errors carry the server's message.
  function remove(path) {
    return api(path, { method: "DELETE" });
  }

  // POST a JSON body (or none) and return the JSON reply; errors carry the server's message.
  function send(path, body) {
    const options = { method: "POST" };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    return api(path, options);
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

  // The seat's agent name, followed by its model id when the name is a label that hides it.
  function seatName(seat) {
    if (!seat) return "";
    return seat.model && !seat.agent.startsWith(seat.model) ? `${seat.agent} (${seat.model})` : seat.agent;
  }

  function seatChip(match, player, extra) {
    const seat = match.seats[player];
    return h("span", { class: "seat" }, h("span", { class: `dot p${player}` }), `P${player + 1} `, h("a", { href: `#/agent/${encodeURIComponent(seat.agent)}` }, seatName(seat)), extra);
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

  // A row's delete control: the first click asks, the second removes the log for good.
  // Matches this server is still playing have none; stop them first.
  function deleteCell(match, playing, state, refresh) {
    const cell = h("td", { class: "row-actions", onclick: (event) => event.stopPropagation() });
    if (playing) return cell;
    if (state.confirming !== match.match_id) {
      cell.append(h("button", { class: "small", title: "Delete this match's log and thoughts file", onclick: () => { state.confirming = match.match_id; refresh(); } }, "Delete"));
      return cell;
    }
    const confirm = async () => {
      state.confirming = null;
      try {
        await remove(`/api/matches/${match.match_id}`);
      } catch (error) {
        return showError(error);
      }
      refresh();
    };
    cell.append(h("button", { class: "small danger", onclick: confirm }, "Delete for good"), " ", h("button", { class: "small", onclick: () => { state.confirming = null; refresh(); } }, "Cancel"));
    return cell;
  }

  async function renderMatches(params, state, refresh) {
    setActiveNav("matches");
    const query = new URLSearchParams();
    if (params.get("game")) query.set("game", params.get("game"));
    if (params.get("agent")) query.set("agent", params.get("agent"));
    const [catalog, gameList, launches] = await Promise.all([api(`/api/matches?${query}`), loadGames(), api("/api/launches")]);
    // The log says running for a paused match; the launcher knows it is paused.
    const paused = new Set(launches.filter((launch) => launch.status === "paused").map((launch) => launch.match_id));
    const shown = catalog.matches.map((match) => (match.status === "running" && paused.has(match.match_id) ? { ...match, status: "paused" } : match));
    const playing = new Set(launches.filter((launch) => ["running", "paused"].includes(launch.status)).map((launch) => launch.match_id));
    const gameSelect = h("select", { onchange: (event) => navigateMatches({ game: event.target.value, agent: params.get("agent") }) }, h("option", { value: "" }, "All games"), gameList.map((g) => h("option", { value: g.id, selected: g.id === params.get("game") ? "" : null }, `${g.id} (${g.matches})`)));
    if (!params.get("game")) gameSelect.value = "";
    const agentInput = h("input", { type: "text", placeholder: "agent name", value: params.get("agent") || "" });
    agentInput.addEventListener("change", () => navigateMatches({ game: params.get("game"), agent: agentInput.value }));
    const toolbar = h("div", { class: "toolbar" }, h("label", {}, "Game ", gameSelect), h("label", {}, "Agent ", agentInput), h("span", { class: "muted small" }, `${catalog.matches.length} matches`));
    const table = h(
      "table",
      {},
      h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "Game"), h("th", {}, "Seats"), h("th", { class: "num" }, "Steps"), h("th", { class: "num" }, "Cost"), h("th", {}, "Status"), h("th", {}))),
      h("tbody", {}, shown.map((match) => {
        const row = matchRow(match);
        row.append(deleteCell(match, playing.has(match.match_id), state, refresh));
        return row;
      })),
    );
    const empty = catalog.matches.length ? null : h("p", { class: "muted" }, "No matches yet. Play one with `arena play` and it appears here.");
    const unreadable = catalog.unreadable.length ? h("p", { class: "small error" }, `${catalog.unreadable.length} log file(s) could not be read: `, catalog.unreadable.map((u) => `${u.path}`).join(", ")) : null;
    app.replaceChildren(h("h1", {}, "Matches"), toolbar, h("div", { class: "panel" }, table, empty), unreadable || "");
    return catalog.matches.some((m) => m.status === "running");
  }

  // The list refreshes every few seconds while a match is running.
  function matchesPage(params) {
    let timer = null;
    let disposed = false;
    // which row's delete is waiting for its second click; kept across refreshes
    const state = { confirming: null };
    const refresh = async () => {
      if (disposed) return;
      const running = await renderMatches(params, state, () => refresh().catch(showError));
      clearTimeout(timer);
      if (running && !disposed) timer = setTimeout(() => refresh().catch(showError), 3000);
    };
    return { start: refresh, dispose: () => { disposed = true; clearTimeout(timer); } };
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

  // Text with each seat mention (P1, P2, ...) in that seat's color.
  function seatColored(text, players) {
    const parts = [];
    let end = 0;
    for (const found of text.matchAll(/\bP(\d+)\b/g)) {
      const player = Number(found[1]) - 1;
      if (player < 0 || player >= players) continue;
      parts.push(text.slice(end, found.index), h("span", { class: `seat-ref c${player}` }, found[0]));
      end = found.index + found[0].length;
    }
    parts.push(text.slice(end));
    return parts;
  }

  // One row per event: the step in a column wide enough for five digits, then the message.
  function eventList(outline, step, viewer, omniscient) {
    const players = outline.match.seats.length;
    const items = visibleEvents(outline, step, viewer, omniscient).map((event) => {
      const isPrivate = event.audience !== "everyone";
      const classes = [];
      if (event.step === step) classes.push("current");
      if (isPrivate) classes.push("private");
      const who = isPrivate ? ` (seen by ${event.audience.map((p) => `P${p + 1}`).join(", ")})` : "";
      return h("li", { class: classes.join(" ") }, h("span", { class: "step" }, event.step), h("span", { class: "text" }, seatColored(event.text + who, players)));
    });
    const list = h("ul", { class: "events" }, items);
    // scroll the list itself, never the page, so controls stay put while a match runs
    requestAnimationFrame(() => {
      const current = list.querySelector(".current");
      if (!current) return;
      const item = current.getBoundingClientRect();
      const box = list.getBoundingClientRect();
      if (item.bottom > box.bottom) list.scrollTop += item.bottom - box.bottom;
      else if (item.top < box.top) list.scrollTop -= box.top - item.top;
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

  // Rebuilds a slot only when `key` changes, so a refresh never swaps a control under the pointer.
  function fill(slot, key, build) {
    if (slot.dataset.key === key) return;
    slot.dataset.key = key;
    slot.replaceChildren(build() || "");
  }

  // A red dot while the page shows the step being played now; grey when paused or scrolled back.
  function liveIndicator(state) {
    const on = state === "on";
    return h("span", { class: on ? "live on" : "live", title: on ? "Showing the move being played now" : "Not showing the latest step, or the match is paused" }, h("span", { class: "live-dot" }), "Live");
  }

  // `launch` (or null) carries the live status, such as paused, of a match this server started.
  // `live` is "on", "off", or null for a match that is not running.
  function matchHeader(match, launch, live) {
    const config = Object.entries(match.config).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ");
    // the launcher knows a match is paused or failed; its log only says running or stopped
    const current = launch && (match.status === "running" || launch.status === "failed") ? { status: launch.status } : match;
    return h(
      "div",
      { class: "match-head" },
      h("div", {}, h("h1", {}, h("a", { href: `#/games/${match.game_id}` }, match.game_id), " ", h("span", { class: "muted mono small" }, match.match_id), " ", statusBadge(current), live ? [" ", liveIndicator(live)] : null), h("div", { class: "muted small mono" }, `seed ${match.seed} · ${config}`)),
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
    // `launch` is set only for matches this server started, which it can pause and stop.
    let launch = null;
    // Bumped by every pause, resume or stop, so an older status poll cannot undo it.
    let launchEpoch = 0;
    // Deleting removes the log for good, so it waits for a second click.
    let confirmingDelete = false;
    // The page's slots and replay controls, built once by `buildView`.
    let view = null;

    const frameOf = async (n) => {
      if (!frames.has(n)) frames.set(n, api(`/api/matches/${matchId}/frames/${n}`));
      return frames.get(n);
    };

    const last = () => outline.frame_count - 1;

    const seek = (n) => {
      step = Math.min(last(), Math.max(0, n));
      if (step === last() && outline.match.status !== "running") stop();
      render();
    };

    const stop = () => {
      playing = false;
      if (timer) clearInterval(timer);
      timer = null;
    };

    const play = () => {
      if (playing) {
        stop();
        return render();
      }
      playing = true;
      timer = setInterval(() => {
        if (step >= last()) {
          if (outline.match.status !== "running") stop();
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

    // While a match runs, a poll may catch the log between a decision and its
    // events; that read fails and the next poll retries.
    const refreshOutline = async () => {
      let fresh;
      try {
        fresh = await api(`/api/matches/${matchId}/timeline`);
      } catch (error) {
        if (outline) return;
        throw error;
      }
      const shown = outline !== null;
      const grew = shown && fresh.frame_count > outline.frame_count;
      const wasAtEnd = shown && step === last();
      const ended = shown && outline.match.status !== fresh.match.status;
      outline = fresh;
      if (grew && wasAtEnd) step = last();
      if (fresh.match.status !== "running" && poll) {
        clearInterval(poll);
        poll = null;
      }
      const launchChanged = await loadLaunch();
      if (shown && (grew || ended || launchChanged)) render();
    };

    // Returns whether the launch status changed; a 404 means another process runs it.
    const loadLaunch = async () => {
      const before = launch && launch.status;
      const epoch = launchEpoch;
      let fresh;
      try {
        fresh = await api(`/api/launches/${matchId}`);
      } catch (error) {
        fresh = null;
      }
      if (epoch !== launchEpoch) return false;
      launch = fresh;
      return before !== (launch && launch.status);
    };

    const act = async (action) => {
      launchEpoch += 1;
      try {
        launch = await send(`/api/launches/${matchId}/${action}`);
        await refreshOutline();
      } catch (error) {
        return showError(error);
      }
      render();
    };

    const liveControls = () => {
      if (!launch || !["running", "paused"].includes(launch.status)) return null;
      const paused = launch.status === "paused";
      const toggle = paused
        ? h("button", { class: "primary", onclick: () => act("resume") }, "Resume match")
        : h("button", { onclick: () => act("pause"), title: "Holds the match before its next round; a model call in progress finishes first." }, "Pause match");
      const stopButton = h("button", { class: "danger", onclick: () => act("stop"), title: "Ends the match now; it cannot be resumed. Its log is kept." }, "Stop match");
      return h("div", { class: "live-controls" }, toggle, stopButton);
    };

    const deleteMatch = async () => {
      try {
        await remove(`/api/matches/${matchId}`);
      } catch (error) {
        return showError(error);
      }
      location.hash = "#/matches";
    };

    // For a match this server is not playing: delete its log, after a second click.
    const deleteControls = () => {
      const ask = () => { confirmingDelete = true; render(); };
      const cancel = () => { confirmingDelete = false; render(); };
      const failure = launch && launch.error ? h("span", { class: "error small" }, `This match failed: ${launch.error}`) : null;
      if (!confirmingDelete) return h("div", { class: "live-controls" }, h("button", { onclick: ask, title: "Removes this match's log and thoughts file." }, "Delete match"), failure);
      return h("div", { class: "live-controls" }, h("button", { class: "danger", onclick: deleteMatch }, "Delete for good"), h("button", { onclick: cancel }, "Cancel"), h("span", { class: "muted small" }, "Its log and thoughts file are removed from disk."));
    };

    // The replay controls stay the same elements for the page's life; `updateControls` refreshes them.
    const buildControls = () => {
      const slider = h("input", { type: "range", min: 0 });
      slider.addEventListener("input", (event) => seek(Number(event.target.value)));
      const playButton = h("button", { onclick: play, title: "play/pause (space)" });
      const stepLabel = h("span", { class: "step mono" });
      const viewerSelect = h("select", {}, h("option", { value: "" }, "Spectator"), outline.match.seats.map((seat) => h("option", { value: seat.player }, `P${seat.player + 1} ${seatName(seat)}`)));
      viewerSelect.value = viewer === null ? "" : String(viewer);
      viewerSelect.addEventListener("change", () => { viewer = viewerSelect.value === "" ? null : Number(viewerSelect.value); render(); });
      const speedSelect = h("select", {}, SPEEDS.map((s) => h("option", { value: s }, `${s}×`)));
      speedSelect.value = String(speed);
      speedSelect.addEventListener("change", () => { speed = Number(speedSelect.value); if (playing) { stop(); play(); } });
      const allEvents = h("input", { type: "checkbox" });
      allEvents.checked = omniscient;
      allEvents.addEventListener("change", () => { omniscient = allEvents.checked; render(); });
      const row = h(
        "div",
        { class: "controls" },
        h("button", { onclick: () => seek(0), title: "first (Home)" }, "⏮"),
        h("button", { onclick: () => seek(step - 1), title: "previous (←)" }, "◀"),
        playButton,
        h("button", { onclick: () => seek(step + 1), title: "next (→)" }, "▶|"),
        h("button", { onclick: () => seek(last()), title: "last (End)" }, "⏭"),
        speedSelect,
        slider,
        stepLabel,
        h("label", {}, "View ", viewerSelect),
        h("label", {}, allEvents, " all events"),
      );
      return { row, slider, playButton, stepLabel };
    };

    const updateControls = () => {
      const { slider, playButton, stepLabel } = view.controls;
      slider.max = last();
      slider.value = step;
      playButton.className = playing ? "primary" : "";
      playButton.textContent = playing ? "⏸" : "▶";
      stepLabel.textContent = `step ${step} / ${last()}`;
    };

    const buildView = () => {
      const controls = buildControls();
      const slots = { header: h("div", {}), bar: h("div", {}), notice: h("div", {}), grid: h("div", { class: "match-grid" }) };
      return { ...slots, controls, root: h("div", {}, slots.header, slots.bar, slots.notice, controls.row, slots.grid) };
    };

    // "on" at the latest step of a match that is playing; "off" when paused or scrolled back.
    const liveState = () => {
      if (outline.match.status !== "running") return null;
      const moving = launch === null || launch.status === "running";
      return moving && step === last() ? "on" : "off";
    };

    const headerKey = (match) => [match.status, launch && launch.status, liveState(), match.seats.map((s) => `${s.rank}/${s.forfeited}`).join(",")].join("|");

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
      if (!view.root.isConnected) app.replaceChildren(view.root);
      fill(view.header, headerKey(match), () => matchHeader(match, launch, liveState()));
      fill(view.bar, `${launch && launch.status}|${confirmingDelete}`, () => liveControls() || deleteControls());
      fill(view.notice, `${outline.replay_error}|${last()}`, () => outline.replay_error
        ? h("p", { class: "panel error small" }, `Only steps 0–${last()} can be shown: this log stops matching the current ${match.game_id} rules after that, probably because the rules changed after it was recorded. `, h("span", { class: "muted" }, outline.replay_error))
        : null);
      updateControls();
      view.grid.replaceChildren(
        h("div", { class: "stack" }, boardPanel(match, frame, viewer, layout), h("div", { class: "panel" }, pointsChart(outline, step, seek))),
        h("div", { class: "stack" }, decisionPanel(match, frame), h("div", { class: "panel" }, h("h3", {}, "Events"), eventList(outline, step, viewer, omniscient))),
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
      view = buildView();
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
  // A route renders the page, or returns {start, dispose} for a page that keeps updating.
  const routes = {
    matches: (_, params) => matchesPage(params),
    match: (args, params) => matchPage(args[0], params),
  };
  // Other scripts add pages to `routes` and reuse these helpers.
  window.viewer = { h, api, send, seatName, loadGames, formatCost, formatSeconds, formatDate, seatChip, matchRow, setActiveNav, showError, routes, app };

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
      if (routes[name]) {
        const page = await routes[name](args, params);
        if (page && page.start) {
          current.dispose = page.dispose;
          await page.start();
        }
      } else {
        app.replaceChildren(h("div", { class: "panel" }, h("p", { class: "error" }, `Unknown page: ${name}`)));
      }
    } catch (error) {
      showError(error);
    }
  }

  window.addEventListener("hashchange", route);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", route);
  else route();
})();
