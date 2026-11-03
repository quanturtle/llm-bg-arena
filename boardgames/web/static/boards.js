// Game-specific board renderers. Each takes the spectator observation of one
// step and a context {layout, frame, match, lastEvents} and returns an element.
// window.eventIcons[game_id] maps a game's event kinds to the icons the event log shows.
window.boards = window.boards || {};
window.eventIcons = window.eventIcons || {};

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

  window.boards.tic_tac_toe = renderTicTacToe;
  window.eventIcons.tic_tac_toe = { started: "🏁", marked: "✏️", won: "🏆", drawn: "🤝" };
})();
