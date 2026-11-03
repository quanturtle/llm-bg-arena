// Catan board renderer: draws one spectator observation as an SVG plus a
// player table. Registers itself as window.boards.catan.
window.boards = window.boards || {};

(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  // Pixels per geometry unit (the hex radius) and the margin around the board.
  const SCALE = 40;
  const MARGIN = 1.5;
  const SEAT_LABELS = ["P1", "P2", "P3", "P4"];

  function svgElement(tag, attributes) {
    const element = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes || {})) {
      element.setAttribute(name, String(value));
    }
    return element;
  }

  function svgText(x, y, text, className) {
    const element = svgElement("text", {
      x: x.toFixed(2),
      y: y.toFixed(2),
      class: className,
      "dominant-baseline": "central",
    });
    element.textContent = text;
    return element;
  }

  function htmlElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = text;
    }
    return element;
  }

  // Geometry y grows upward; SVG y grows downward.
  function toSvg(point) {
    return { x: point.x * SCALE, y: -point.y * SCALE };
  }

  function pointsAttribute(points) {
    return points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
  }

  function viewBox(layout) {
    const xs = layout.vertices.map((vertex) => vertex.x);
    const ys = layout.vertices.map((vertex) => vertex.y);
    const left = (Math.min(...xs) - MARGIN) * SCALE;
    const top = (-Math.max(...ys) - MARGIN) * SCALE;
    const width = (Math.max(...xs) - Math.min(...xs) + 2 * MARGIN) * SCALE;
    const height = (Math.max(...ys) - Math.min(...ys) + 2 * MARGIN) * SCALE;
    return `${left.toFixed(2)} ${top.toFixed(2)} ${width.toFixed(2)} ${height.toFixed(2)}`;
  }

  function drawNumberToken(group, centre, number) {
    const hot = number === 6 || number === 8;
    group.appendChild(
      svgElement("circle", {
        cx: centre.x.toFixed(2),
        cy: centre.y.toFixed(2),
        r: (0.32 * SCALE).toFixed(2),
        class: "token" + (hot ? " hot" : ""),
      })
    );
    group.appendChild(svgText(centre.x, centre.y, String(number), "number" + (hot ? " hot" : "")));
  }

  // The robber stands beside the number token, clear of the six corners.
  function drawRobber(group, centre) {
    const x = centre.x + 0.5 * SCALE;
    const y = centre.y;
    const robber = svgElement("g", { class: "robber" });
    robber.appendChild(
      svgElement("circle", { cx: x.toFixed(2), cy: (y - 0.18 * SCALE).toFixed(2), r: (0.11 * SCALE).toFixed(2) })
    );
    robber.appendChild(
      svgElement("path", {
        d:
          `M ${(x - 0.16 * SCALE).toFixed(2)} ${(y + 0.18 * SCALE).toFixed(2)} ` +
          `Q ${(x - 0.14 * SCALE).toFixed(2)} ${(y - 0.1 * SCALE).toFixed(2)} ${x.toFixed(2)} ${(y - 0.08 * SCALE).toFixed(2)} ` +
          `Q ${(x + 0.14 * SCALE).toFixed(2)} ${(y - 0.1 * SCALE).toFixed(2)} ${(x + 0.16 * SCALE).toFixed(2)} ${(y + 0.18 * SCALE).toFixed(2)} Z`,
      })
    );
    const title = svgElement("title");
    title.textContent = "robber";
    robber.appendChild(title);
    group.appendChild(robber);
  }

  function drawHexes(svg, layout, observation) {
    const group = svgElement("g", { class: "hexes" });
    const hexes = observation.hexes || [];
    layout.hexes.forEach((hex, hexId) => {
      const data = hexes[hexId] || {};
      const corners = layout.hex_vertices[hexId].map((vertexId) => toSvg(layout.vertices[vertexId]));
      const centre = toSvg(hex);
      group.appendChild(
        svgElement("polygon", {
          points: pointsAttribute(corners),
          class: `hex ${data.terrain || "unknown"}`,
        })
      );
      group.appendChild(svgText(centre.x, centre.y - 0.62 * SCALE, `h${hexId}`, "hex-label"));
      if (data.number !== null && data.number !== undefined) {
        drawNumberToken(group, centre, data.number);
      }
      if (observation.robber === hexId) {
        drawRobber(group, centre);
      }
    });
    svg.appendChild(group);
  }

  function portLabel(port) {
    return port.resource === null || port.resource === undefined ? "3:1" : `2:1 ${port.resource}`;
  }

  // A port sits on a coastal edge; the marker is pushed outward from the board
  // centre at the origin, along the edge's midpoint direction.
  function drawPorts(svg, layout, observation) {
    const group = svgElement("g", { class: "ports" });
    for (const port of observation.ports || []) {
      const edge = layout.edges[port.edge];
      if (!edge) {
        continue;
      }
      const [first, second] = edge.vertices.map((vertexId) => toSvg(layout.vertices[vertexId]));
      const midpoint = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
      const distance = Math.hypot(midpoint.x, midpoint.y) || 1;
      const marker = {
        x: midpoint.x + (midpoint.x / distance) * 0.62 * SCALE,
        y: midpoint.y + (midpoint.y / distance) * 0.62 * SCALE,
      };
      const kind = port.resource === null || port.resource === undefined ? "any" : String(port.resource);
      const item = svgElement("g", { class: `port port-${kind}` });
      item.appendChild(
        svgElement("line", {
          x1: midpoint.x.toFixed(2),
          y1: midpoint.y.toFixed(2),
          x2: marker.x.toFixed(2),
          y2: marker.y.toFixed(2),
          class: "port-link",
        })
      );
      const width = 1.25 * SCALE;
      const height = 0.5 * SCALE;
      item.appendChild(
        svgElement("rect", {
          x: (marker.x - width / 2).toFixed(2),
          y: (marker.y - height / 2).toFixed(2),
          width: width.toFixed(2),
          height: height.toFixed(2),
          rx: (height / 2).toFixed(2),
          class: "port-pill",
        })
      );
      item.appendChild(svgText(marker.x, marker.y, portLabel(port), "port-label"));
      const title = svgElement("title");
      title.textContent = `e${port.edge} ${portLabel(port)}`;
      item.appendChild(title);
      group.appendChild(item);
    }
    svg.appendChild(group);
  }

  function drawEdges(svg, layout) {
    const group = svgElement("g", { class: "edges" });
    for (const edge of layout.edges) {
      const [first, second] = edge.vertices.map((vertexId) => toSvg(layout.vertices[vertexId]));
      group.appendChild(
        svgElement("line", {
          x1: first.x.toFixed(2),
          y1: first.y.toFixed(2),
          x2: second.x.toFixed(2),
          y2: second.y.toFixed(2),
          class: "edge",
        })
      );
    }
    svg.appendChild(group);
  }

  // Roads stop short of both intersections so buildings stay visible.
  function drawRoads(svg, layout, observation) {
    const group = svgElement("g", { class: "roads" });
    const roads = observation.roads || [];
    roads.forEach((owner, edgeId) => {
      const edge = layout.edges[edgeId];
      if (owner === null || owner === undefined || !edge) {
        return;
      }
      const [first, second] = edge.vertices.map((vertexId) => toSvg(layout.vertices[vertexId]));
      const dx = second.x - first.x;
      const dy = second.y - first.y;
      const length = Math.hypot(dx, dy) || 1;
      const inset = 0.2 * SCALE;
      const road = svgElement("line", {
        x1: (first.x + (dx / length) * inset).toFixed(2),
        y1: (first.y + (dy / length) * inset).toFixed(2),
        x2: (second.x - (dx / length) * inset).toFixed(2),
        y2: (second.y - (dy / length) * inset).toFixed(2),
        class: `road owner-${owner}`,
      });
      const title = svgElement("title");
      title.textContent = `e${edgeId} ${SEAT_LABELS[owner] || `P${owner + 1}`} road`;
      road.appendChild(title);
      group.appendChild(road);
    });
    svg.appendChild(group);
  }

  function drawVertices(svg, layout) {
    const group = svgElement("g", { class: "vertices" });
    for (const vertex of layout.vertices) {
      const point = toSvg(vertex);
      group.appendChild(
        svgElement("circle", {
          cx: point.x.toFixed(2),
          cy: point.y.toFixed(2),
          r: (0.05 * SCALE).toFixed(2),
          class: "vertex",
        })
      );
    }
    svg.appendChild(group);
  }

  function settlementPoints(centre) {
    const size = 0.17 * SCALE;
    return [
      { x: centre.x - size, y: centre.y + size },
      { x: centre.x - size, y: centre.y - size * 0.3 },
      { x: centre.x, y: centre.y - size * 1.2 },
      { x: centre.x + size, y: centre.y - size * 0.3 },
      { x: centre.x + size, y: centre.y + size },
    ];
  }

  function cityPoints(centre) {
    const size = 0.24 * SCALE;
    return [
      { x: centre.x - size, y: centre.y + size * 0.8 },
      { x: centre.x - size, y: centre.y - size * 0.3 },
      { x: centre.x - size * 0.5, y: centre.y - size },
      { x: centre.x, y: centre.y - size * 0.3 },
      { x: centre.x + size, y: centre.y - size * 0.3 },
      { x: centre.x + size, y: centre.y + size * 0.8 },
    ];
  }

  function drawBuildings(svg, layout, observation) {
    const group = svgElement("g", { class: "buildings" });
    const buildings = observation.buildings || [];
    buildings.forEach((building, vertexId) => {
      const vertex = layout.vertices[vertexId];
      if (!building || !vertex) {
        return;
      }
      const centre = toSvg(vertex);
      const isCity = building.kind === "city";
      const shape = svgElement("polygon", {
        points: pointsAttribute(isCity ? cityPoints(centre) : settlementPoints(centre)),
        class: `building ${isCity ? "city" : "settlement"} owner-${building.player}`,
      });
      const title = svgElement("title");
      title.textContent = `v${vertexId} ${SEAT_LABELS[building.player] || `P${building.player + 1}`} ${building.kind}`;
      shape.appendChild(title);
      group.appendChild(shape);
    });
    svg.appendChild(group);
  }

  function boardSvg(layout, observation) {
    const svg = svgElement("svg", {
      viewBox: viewBox(layout),
      xmlns: SVG_NS,
      role: "img",
    });
    drawHexes(svg, layout, observation);
    drawPorts(svg, layout, observation);
    drawEdges(svg, layout);
    drawRoads(svg, layout, observation);
    drawVertices(svg, layout);
    drawBuildings(svg, layout, observation);
    return svg;
  }

  function seatName(context, player) {
    const seats = context && context.match && Array.isArray(context.match.seats) ? context.match.seats : [];
    const seat = seats[player];
    const label = SEAT_LABELS[player] || `P${player + 1}`;
    return seat && seat.agent ? `${label} ${window.viewer.seatName(seat)}` : label;
  }

  function statusText(observation, context) {
    if (observation.game_over) {
      const winner = observation.winner;
      return winner === null || winner === undefined
        ? "Game over."
        : `Game over: ${seatName(context, winner)} won.`;
    }
    const parts = [`Turn ${observation.turn}`, String(observation.phase || "").replace(/_/g, " ")];
    if (Array.isArray(observation.dice)) {
      const total = observation.dice.reduce((sum, value) => sum + value, 0);
      parts.push(`roll ${observation.dice.join(" + ")} = ${total}`);
    }
    return parts.join(" · ");
  }

  // The player's name, marked winner once the game is over.
  function seatCell(context, player, isWinner) {
    const cell = htmlElement("td");
    const seat = htmlElement("span", "seat");
    seat.appendChild(htmlElement("span", `dot p${player}`));
    seat.appendChild(htmlElement("span", null, seatName(context, player)));
    if (isWinner) seat.appendChild(htmlElement("span", "badge winner", "🏆 winner"));
    cell.appendChild(seat);
    return cell;
  }

  function numberCell(value) {
    return htmlElement("td", "num", value === null || value === undefined ? "" : String(value));
  }

  function awardCell(observation, player) {
    const cell = htmlElement("td", "num awards");
    if (observation.longest_road === player) {
      cell.appendChild(htmlElement("span", "badge", "🏅 longest road"));
    }
    if (observation.largest_army === player) {
      cell.appendChild(htmlElement("span", "badge", "🛡️ largest army"));
    }
    return cell;
  }

  const DEV_CARD_NAMES = {
    knight: "⚔️ knight",
    road_building: "🚧 road building",
    year_of_plenty: "🌈 year of plenty",
    monopoly: "💰 monopoly",
    victory_point: "⭐ victory point",
  };

  // A player's card count, with the kinds below it once the game ends and reveals them.
  function devCell(observation, player) {
    const count = (observation.dev_counts || [])[player];
    const cell = htmlElement("td", "num dev-cards", count === undefined ? "" : String(count));
    const cards = observation.revealed_dev ? observation.revealed_dev[player] : null;
    const names = Object.entries(cards || {})
      .filter(([, copies]) => copies > 0)
      .map(([kind, copies]) => `${DEV_CARD_NAMES[kind] || kind}${copies > 1 ? ` ×${copies}` : ""}`);
    if (names.length) cell.appendChild(htmlElement("div", "muted small", names.join(", ")));
    return cell;
  }

  // Public points during play, which leave out hidden victory-point cards; final scores once the game ends.
  function victoryPoints(observation, player) {
    if (observation.final_scores) {
      const score = observation.final_scores.find((entry) => entry.player === player);
      return score ? score.points : null;
    }
    return (observation.public_points || [])[player];
  }

  function playerTable(observation, context) {
    const table = htmlElement("table", "players");
    const head = htmlElement("thead");
    const headRow = htmlElement("tr");
    for (const [label, className, title] of [
      ["Player", ""],
      ["🏆 VP", "num", "Victory points others can see; hidden victory-point cards count once the game ends."],
      ["✋ Hand", "num", "Resource cards in hand."],
      ["🃏 Development cards", "num", "Cards in hand; their kinds stay hidden until the game ends. A seat picked under View lists its own cards in the text view."],
      ["⚔️ Knights", "num", "Knights played."],
      ["🎖️ Awards", "num"],
    ]) {
      const cell = htmlElement("th", className, label);
      if (title) cell.title = title;
      headRow.appendChild(cell);
    }
    head.appendChild(headRow);
    table.appendChild(head);
    const body = htmlElement("tbody");
    const count = (observation.hand_sizes || observation.public_points || []).length;
    for (let player = 0; player < count; player += 1) {
      const row = htmlElement("tr", observation.active === player && !observation.game_over ? "active" : "");
      row.appendChild(seatCell(context, player, Boolean(observation.game_over) && observation.winner === player));
      row.appendChild(numberCell(victoryPoints(observation, player)));
      row.appendChild(numberCell((observation.hand_sizes || [])[player]));
      row.appendChild(devCell(observation, player));
      row.appendChild(numberCell((observation.knights || [])[player]));
      row.appendChild(awardCell(observation, player));
      body.appendChild(row);
    }
    table.appendChild(body);
    return table;
  }

  function renderCatan(observation, context) {
    const layout = context && context.layout;
    const root = htmlElement("div", "catan");
    if (!layout || !Array.isArray(layout.hexes)) {
      root.appendChild(htmlElement("p", "error", "Catan layout missing."));
      return root;
    }
    root.appendChild(boardSvg(layout, observation || {}));
    root.appendChild(htmlElement("div", "status small muted", statusText(observation || {}, context)));
    root.appendChild(playerTable(observation || {}, context));
    return root;
  }

  window.boards.catan = renderCatan;
  window.eventIcons = window.eventIcons || {};
  window.eventIcons.catan = {
    started: "🏁", board_prepared: "🗺️", setup_started: "🏁", setup_turn: "👉", setup_road_skipped: "⏭️", setup_complete: "✅",
    starting_resources: "🎁", turn_started: "▶️", turn_ended: "⏹️", dice_rolled: "🎲", production: "🌾", seven_rolled: "7️⃣",
    discard_notice: "⚠️", discarded: "🗑️", robber_moved: "🦹", stolen: "🫳", stole_card: "🫳", card_stolen: "🫳",
    road_built: "🛣️", settlement_built: "🏠", city_built: "🏙️",
    bank_trade: "🏦", offer_made: "💬", offer_accepted: "🤝", offer_declined: "🙅",
    dev_bought: "🃏", dev_drawn: "🃏", knight_played: "⚔️", monopoly_played: "💰", year_of_plenty_played: "🌈",
    road_building_played: "🚧", free_roads_exhausted: "🚧",
    longest_road: "🏅", longest_road_lost: "🏅", largest_army: "🛡️", largest_army_lost: "🛡️", game_over: "🏆",
  };
})();
