// Game-specific board renderers. Each takes the spectator observation of one
// step and a context {layout, frame, match, lastEvents} and returns an element.
window.boards = window.boards || {};

(function () {
  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (key === "class") node.className = value;
      else if (key === "style") node.style.cssText = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const MARK_SEAT = { X: 0, O: 1 };

  function cellName(row, col) {
    return String.fromCharCode(97 + col) + (row + 1);
  }

  // Tic-tac-toe: `board` lists rows top first; row 1 is the bottom line.
  function renderTicTacToe(observation, context) {
    const rows = observation.board.length;
    const cols = observation.board[0].length;
    const winning = new Set(observation.line || []);
    const marked = (context.lastEvents || []).find((e) => e.kind === "marked");
    const last = marked ? marked.data.cell : null;
    const grid = h("div", {
      class: "grid-board",
      style: `grid-template-columns: 24px repeat(${cols}, 38px)`,
    });
    observation.board.forEach((line, index) => {
      const row = rows - 1 - index;
      grid.append(h("div", { class: "label row" }, row + 1));
      for (let col = 0; col < cols; col += 1) {
        const mark = line[col];
        const name = cellName(row, col);
        const classes = ["cell"];
        if (winning.has(name)) classes.push("win");
        if (name === last) classes.push("last");
        const seat = MARK_SEAT[mark];
        const style = seat === undefined ? "" : `color: var(--p${seat + 1})`;
        grid.append(h("div", { class: classes.join(" "), style, title: name }, mark === "." ? "" : mark));
      }
    });
    grid.append(h("div", { class: "label" }, ""));
    for (let col = 0; col < cols; col += 1) {
      grid.append(h("div", { class: "label" }, String.fromCharCode(97 + col)));
    }
    let status;
    if (observation.winner !== null && observation.winner !== undefined) {
      status = `P${observation.winner + 1} wins with ${observation.line.join(" ")}.`;
    } else if (observation.is_draw) {
      status = "Draw.";
    } else {
      status = `P${observation.to_move + 1} to move.`;
    }
    return h("div", {}, grid, h("p", { class: "muted small" }, status));
  }

  const LOT_COLORS = { red: "#d94a3d", green: "#2e8b57", blue: "#2f6fde", yellow: "#d9a21b", purple: "#8e44ad", orange: "#e67e22" };

  function lotChip(lot) {
    const [color] = lot.split(" ");
    const fill = LOT_COLORS[color] || "var(--muted)";
    return h("span", { class: "badge", style: `border-color: ${fill}; color: ${fill}` }, lot);
  }

  // Sealed auction: the lot on the block, then one row per bidder.
  function renderAuction(observation, context) {
    const seats = context.match.seats;
    const head = observation.current_lot
      ? h("div", {}, h("span", { class: "muted small" }, `Round ${observation.round} of ${observation.total_rounds}: `), h("span", { class: "lot" }, observation.current_lot))
      : h("div", { class: "lot" }, "Auction over");
    const rows = seats.map((seat, i) =>
      h(
        "tr",
        {},
        h("td", {}, h("span", { class: "seat" }, h("span", { class: `dot p${i}` }), `P${i + 1} ${window.viewer.seatName(seat)}`)),
        h("td", { class: "num" }, observation.coins[i]),
        h("td", {}, observation.won[i].length ? observation.won[i].map(lotChip) : h("span", { class: "muted" }, "none")),
        h("td", {}, observation.has_bid[i] ? "sealed" : h("span", { class: "muted" }, "waiting")),
        h("td", {}, observation.revealed_colors ? lotChip(observation.revealed_colors[i]) : h("span", { class: "muted" }, "secret")),
      ),
    );
    const table = h(
      "table",
      {},
      h("thead", {}, h("tr", {}, h("th", {}, "Player"), h("th", { class: "num" }, "Coins"), h("th", {}, "Won lots"), h("th", {}, "Bid"), h("th", {}, "Color"))),
      h("tbody", {}, rows),
    );
    return h("div", { class: "auction stack" }, head, table);
  }

  window.boards.tic_tac_toe = renderTicTacToe;
  window.boards.sealed_auction = renderAuction;
})();
