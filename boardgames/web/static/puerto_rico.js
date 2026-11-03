// Puerto Rico board renderer: draws one spectator observation as role cards,
// the common table and every player's island and city. Registers itself as
// window.boards.puerto_rico.
window.boards = window.boards || {};

(function () {
  const ASSET_ROOT = "/static/puerto_rico";
  const COIN_1 = "tokens/doubloon_1.png";
  const COIN_5 = "tokens/doubloon_5.png";
  const GOODS = ["corn", "indigo", "sugar", "tobacco", "coffee"];
  const GOOD_META = {
    corn: {
      label: "Corn",
      icon: "🌽",
      barrel: "goods/corn_barrel.png",
      tile: "plantations/corn.png",
      occupied: "plantations/corn_occupied.png",
    },
    indigo: {
      label: "Indigo",
      icon: "🔷",
      barrel: "goods/indigo_barrel.png",
      tile: "plantations/indigo.png",
      occupied: "plantations/indigo_occupied.png",
    },
    sugar: {
      label: "Sugar",
      icon: "🍬",
      barrel: "goods/sugar_barrel.png",
      tile: "plantations/sugar.png",
      occupied: "plantations/sugar_occupied.png",
    },
    tobacco: {
      label: "Tobacco",
      icon: "🍂",
      barrel: "goods/tobacco_barrel.png",
      tile: "plantations/tobacco.png",
      occupied: "plantations/tobacco_occupied.png",
    },
    coffee: {
      label: "Coffee",
      icon: "☕",
      barrel: "goods/coffee_barrel.png",
      tile: "plantations/coffee.png",
      occupied: "plantations/coffee_occupied.png",
    },
  };
  const ROLE_META = {
    settler: { label: "Settler", icon: "🌱", art: "roles/settler.png" },
    mayor: { label: "Mayor", icon: "👤", art: "roles/mayor.png" },
    builder: { label: "Builder", icon: "🔨", art: "roles/builder.png" },
    craftsman: { label: "Craftsman", icon: "⚙️", art: "roles/craftsman.png" },
    trader: { label: "Trader", icon: "💰", art: "roles/trader.png" },
    captain: { label: "Captain", icon: "⛵", art: "roles/captain.png" },
    prospector: { label: "Prospector", icon: "⛏️", art: "roles/prospector.png" },
    prospector_2: { label: "Prospector II", icon: "⛏️", art: "roles/prospector.png" },
  };
  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "style") node.style.cssText = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function asset(path) {
    return `${ASSET_ROOT}/${path}`;
  }

  function image(path, className, alt) {
    return h("img", {
      class: className,
      src: asset(path),
      alt: alt || "",
      loading: "lazy",
    });
  }

  // Building art has one variant per colonist count: name.png, name_1.png, ...
  function buildingArt(name, colonists) {
    const filled = Math.max(0, Math.min(Number(colonists) || 0, 3));
    return `buildings/${name}${filled ? `_${filled}` : ""}.png`;
  }

  function coinIcon(value) {
    return image(Number(value) >= 5 ? COIN_5 : COIN_1, "coin", "doubloon");
  }

  function agentName(context, player) {
    const seat = context && context.match && context.match.seats && context.match.seats[player];
    return seat ? window.viewer.seatName(seat) : `P${player + 1}`;
  }

  function seatText(context, player) {
    return `P${player + 1} ${agentName(context, player)}`;
  }

  function seatDot(player) {
    return h("span", { class: `dot p${player}` });
  }

  function goodClass(good) {
    return `good-${good}`;
  }

  function goodChip(good, count) {
    const meta = GOOD_META[good] || { label: good, icon: "•" };
    return h(
      "span",
      {
        class: `pr-good ${goodClass(good)}`,
        title: count === undefined || count === null ? meta.label : `${meta.label}: ${count}`,
      },
      meta.barrel
        ? image(meta.barrel, "glyph-art", meta.label)
        : h("span", { class: "glyph" }, meta.icon),
      h("span", null, meta.label),
      count === undefined || count === null ? null : h("strong", null, count),
    );
  }

  function goodsRow(goods, showEmpty) {
    const counts = goods || {};
    const names = showEmpty ? GOODS : GOODS.filter((good) => (counts[good] || 0) > 0);
    if (!names.length) return h("span", { class: "muted small" }, "none");
    return h("div", { class: "pr-goods" }, names.map((good) => goodChip(good, counts[good] || 0)));
  }

  function plantationTile(good, colonized) {
    const meta = GOOD_META[good] || { label: good, icon: "•" };
    const art = colonized ? meta.occupied : meta.tile;
    return h(
      "div",
      {
        class: `pr-tile ${goodClass(good)}${colonized ? " colonized" : ""}`,
        title: `${meta.label} plantation${colonized ? " (colonized)" : ""}`,
      },
      art ? image(art, "tile-art", meta.label) : h("span", { class: "icon" }, meta.icon),
      h("span", { class: "label" }, meta.label),
    );
  }

  function quarryTile(occupied) {
    return h(
      "div",
      { class: `pr-tile quarry${occupied ? " colonized" : ""}`, title: occupied ? "Quarry (occupied)" : "Quarry" },
      image(occupied ? "plantations/quarry_occupied.png" : "plantations/quarry.png", "tile-art", "Quarry"),
      h("span", { class: "label" }, "Quarry"),
    );
  }

  function emptyTile() {
    return h("div", { class: "pr-tile empty", title: "empty island space" }, h("span", { class: "icon" }, "·"));
  }

  function islandGrid(player) {
    const tiles = [];
    for (const plantation of player.plantations || []) {
      tiles.push(plantationTile(plantation.good, plantation.colonized));
    }
    const quarries = player.quarries || 0;
    const occupied = player.occupied_quarries || 0;
    for (let index = 0; index < quarries; index += 1) {
      tiles.push(quarryTile(index < occupied));
    }
    while (tiles.length < 12) tiles.push(emptyTile());
    return h("div", { class: "pr-island" }, tiles.slice(0, 12));
  }

  function shipCard(ship, index) {
    const meta = ship.good ? GOOD_META[ship.good] : null;
    const pips = [];
    for (let slot = 0; slot < ship.capacity; slot += 1) {
      pips.push(h("span", { class: `pip${slot < ship.filled ? " filled" : ""}` }));
    }
    return h(
      "div",
      { class: `pr-ship ${ship.good ? goodClass(ship.good) : ""}`, title: `Cargo ship ${index + 1}` },
      h(
        "div",
        { class: "pr-ship-head" },
        meta && meta.barrel
          ? image(meta.barrel, "cargo-art", meta.label)
          : h("span", { class: "icon" }, "⛵"),
        h("span", { class: "name" }, meta ? meta.label : "empty"),
        h("span", { class: "count" }, `${ship.filled}/${ship.capacity}`),
      ),
      h("div", { class: "pips" }, pips),
    );
  }

  function tradingHouse(observation) {
    const slots = [];
    for (let index = 0; index < 4; index += 1) {
      const good = (observation.trading_house || [])[index];
      const meta = good ? GOOD_META[good] : null;
      slots.push(
        h(
          "div",
          {
            class: `pr-slot${good ? ` filled ${goodClass(good)}` : ""}`,
            title: meta ? meta.label : "empty trading-house space",
          },
          meta && meta.barrel
            ? image(meta.barrel, "slot-art", meta.label)
            : meta
              ? meta.icon
              : "",
        ),
      );
    }
    return h(
      "div",
      { class: "pr-trading" },
      h("div", { class: "pr-slots" }, slots),
      image("boards/trading_house.png", "reference-art", "Trading house reference card"),
    );
  }

  function roleCard(role, observation) {
    const meta = ROLE_META[role.role] || { label: role.role, icon: "•" };
    const taken = role.taken_by !== null && role.taken_by !== undefined;
    const active = observation.active_role === role.role;
    const classes = ["pr-role"];
    if (taken) classes.push("taken");
    if (active) classes.push("active");
    return h(
      "div",
      { class: classes.join(" "), title: meta.label },
      meta.art
        ? image(meta.art, "role-art", meta.label)
        : h("span", { class: "icon" }, meta.icon),
      h("span", { class: "name" }, meta.label),
      h(
        "span",
        { class: "meta" },
        role.doubloons
          ? h(
              "span",
              { class: "doubloons", title: "doubloons on this role" },
              coinIcon(role.doubloons),
              `${role.doubloons}d`,
            )
          : null,
        taken
          ? h("span", { class: "seat" }, seatDot(role.taken_by), `P${role.taken_by + 1}`)
          : h("span", { class: "muted" }, "open"),
      ),
    );
  }

  function rolesPanel(observation) {
    return h("div", { class: "pr-roles" }, (observation.roles || []).map((role) => roleCard(role, observation)));
  }

  function suppliesPanel(observation) {
    return h(
      "div",
      { class: "pr-supplies" },
      h(
        "div",
        { class: "pr-supply" },
        h("h4", {}, "Supply"),
        h(
          "div",
          { class: "pr-statline" },
          h("span", {}, "Colonist ship ", h("strong", {}, observation.colonist_ship)),
          h("span", {}, "Colonists ", h("strong", {}, observation.colonist_supply)),
          h("span", {}, "VP chips ", h("strong", {}, observation.vp_supply)),
          h("span", {}, "Quarries ", h("strong", {}, observation.quarry_supply)),
          h("span", {}, "Plantation deck ", h("strong", {}, observation.plantation_deck_count)),
        ),
      ),
      h("div", { class: "pr-supply" }, h("h4", {}, "Goods bank"), goodsRow(observation.goods_supply, true)),
      h("div", { class: "pr-supply" }, h("h4", {}, "Trading house"), tradingHouse(observation)),
      h(
        "div",
        { class: "pr-supply" },
        h("h4", {}, "Cargo ships"),
        h("div", { class: "pr-ships" }, (observation.cargo_ships || []).map(shipCard)),
      ),
      h(
        "div",
        { class: "pr-supply" },
        h("h4", {}, "Face-up plantations"),
        (observation.face_up || []).length
          ? h("div", { class: "pr-tiles" }, observation.face_up.map((good) => plantationTile(good, false)))
          : h("span", { class: "muted small" }, "none"),
      ),
    );
  }

  function buildingSpecs(layout) {
    const specs = new Map();
    for (const spec of (layout && layout.buildings) || []) specs.set(spec.name, spec);
    return specs;
  }

  function buildingLabel(name) {
    return String(name).replace(/_/g, " ");
  }

  function buildingChip(building, spec) {
    const max = spec ? spec.max_colonists : Math.max(1, building.colonists || 0);
    const pips = [];
    for (let slot = 0; slot < max; slot += 1) {
      pips.push(h("span", { class: `pip${slot < (building.colonists || 0) ? " filled" : ""}` }));
    }
    return h(
      "span",
      {
        class: `pr-building${building.active ? " active" : ""}`,
        title: spec
          ? `${buildingLabel(building.name)} (${spec.victory_points} VP, ${building.colonists}/${spec.max_colonists} colonists)`
          : buildingLabel(building.name),
      },
      image(buildingArt(building.name, building.colonists), "building-art", buildingLabel(building.name)),
      h("span", { class: "name" }, buildingLabel(building.name)),
      spec ? h("span", { class: "vp" }, `${spec.victory_points}vp`) : null,
      h("span", { class: "pips" }, pips),
      building.active ? h("span", { class: "badge" }, "active") : null,
    );
  }

  function playerCard(player, observation, context, specs) {
    const active = observation.active === player.seat && !observation.game_over;
    const governor = observation.governor === player.seat;
    const buildings = (player.buildings || []).map((building) =>
      buildingChip(building, specs.get(building.name)),
    );
    const stats = [
      ["Doubloons", player.doubloons, true],
      ["Public VP", player.public_points],
      ["Unplaced colonists", player.colonists_unplaced],
      ["Island", `${player.occupied_island_spaces}/12`],
      ["City", `${player.city_spaces_used}/12`],
    ];
    const classes = ["pr-player"];
    if (active) classes.push("active");
    return h(
      "section",
      { class: classes.join(" ") },
      governor || active
        ? h(
            "div",
            { class: "pr-player-tabs" },
            governor ? h("span", { class: "badge" }, "governor") : null,
            active ? h("span", { class: "badge winner" }, "active") : null,
          )
        : null,
      h(
        "div",
        { class: "pr-player-head" },
        h("span", { class: "seat" }, seatDot(player.seat), seatText(context, player.seat)),
        h("span", { class: "vp" }, `${player.public_points} VP`),
      ),
      h(
        "div",
        { class: "pr-player-stats" },
        stats.map(([label, value, coin]) =>
          h(
            "span",
            {},
            `${label} `,
            coin ? coinIcon(value) : null,
            h("strong", {}, value),
          ),
        ),
      ),
      h("div", { class: "pr-player-row" }, h("span", { class: "label" }, "Goods"), goodsRow(player.goods, false)),
      h("div", { class: "pr-player-row" }, h("span", { class: "label" }, "Island"), islandGrid(player)),
      h(
        "div",
        { class: "pr-player-row" },
        h("span", { class: "label" }, `City (${player.city_spaces_used}/12 spaces)`),
        buildings.length
          ? h("div", { class: "pr-buildings" }, buildings)
          : h("span", { class: "muted small" }, "no buildings"),
      ),
    );
  }

  function buildingMarket(observation, specs) {
    const available = observation.available_buildings || [];
    const counts = {};
    for (const name of available) counts[name] = (counts[name] || 0) + 1;
    const cards = [];
    for (const spec of specs.values()) {
      const copies = counts[spec.name] || 0;
      const meta = spec.production ? GOOD_META[spec.production] : null;
      cards.push(
        h(
          "div",
          { class: `pr-market-card${copies ? "" : " unavailable"}` },
          image(buildingArt(spec.name, 0), "market-art", buildingLabel(spec.name)),
          h(
            "div",
            { class: "pr-market-head" },
            h("span", { class: "name" }, buildingLabel(spec.name)),
            h("span", { class: "vp" }, `${spec.victory_points}vp`),
          ),
          h(
            "div",
            { class: "pr-market-meta" },
            h("span", {}, `cost ${spec.cost}`),
            h("span", {}, `colonists ${spec.max_colonists}`),
            h("span", {}, `left ${copies}`),
            meta ? h("span", {}, `makes ${meta.label}`) : null,
          ),
        ),
      );
    }
    return h(
      "details",
      { class: "pr-market" },
      h("summary", {}, "Building market"),
      h("div", { class: "pr-market-grid" }, cards),
    );
  }

  function finalScores(observation, context) {
    const rows = (observation.final_scores || []).map((score) =>
      h(
        "tr",
        {},
        h("td", {}, h("span", { class: "seat" }, seatDot(score.player), seatText(context, score.player), observation.winner === score.player ? h("span", { class: "badge winner" }, "🏆 winner") : null)),
        h("td", { class: "num" }, score.points),
        h("td", { class: "num" }, score.vp_chips),
        h("td", { class: "mono small" }, JSON.stringify(score.breakdown)),
      ),
    );
    return h(
      "div",
      { class: "pr-final" },
      h("h3", {}, "Final scores"),
      h(
        "table",
        {},
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", {}, "Player"),
            h("th", { class: "num" }, "Points"),
            h("th", { class: "num" }, "VP chips"),
            h("th", {}, "Breakdown"),
          ),
        ),
        h("tbody", {}, rows),
      ),
    );
  }

  function statusBar(observation, context) {
    if (observation.game_over) {
      const winner = observation.winner;
      const reason = observation.end_reason ? ` (${observation.end_reason})` : "";
      return h(
        "div",
        { class: "pr-status pr-game-over" },
        winner !== null && winner !== undefined
          ? `Game over: ${seatText(context, winner)} won${reason}.`
          : `Game over${reason}.`,
      );
    }
    const active = observation.active;
    const role = observation.active_role;
    const order = (observation.order || []).map((player) => `P${player + 1}`).join(" → ");
    return h(
      "div",
      { class: "pr-status" },
      h("strong", {}, `Round ${observation.round}`),
      " · ",
      h("span", { class: "muted" }, String(observation.phase || "").replace(/_/g, " ")),
      " · ",
      h("span", { class: "seat" }, seatDot(active), seatText(context, active)),
      role ? ` chose ${role}` : " acts",
      " · ",
      h("span", { class: "muted" }, `order ${order}`),
    );
  }

  function renderPuertoRico(observation, context) {
    observation = observation || {};
    const specs = buildingSpecs(context && context.layout);
    const root = h("div", { class: "puerto-rico" });
    root.append(statusBar(observation, context));
    root.append(h("div", { class: "pr-section" }, h("h3", {}, "Roles"), rolesPanel(observation)));
    root.append(h("div", { class: "pr-section" }, h("h3", {}, "Table"), suppliesPanel(observation)));
    root.append(
      h(
        "div",
        { class: "pr-section" },
        h("h3", {}, "Players"),
        h(
          "div",
          { class: "pr-players" },
          (observation.players || []).map((player) => playerCard(player, observation, context, specs)),
        ),
      ),
    );
    if (specs.size) root.append(buildingMarket(observation, specs));
    if (observation.game_over) root.append(finalScores(observation, context));
    return root;
  }

  window.boards.puerto_rico = renderPuertoRico;
  window.eventIcons = window.eventIcons || {};
  window.eventIcons.puerto_rico = {
    game_started: "🏁", role_selection: "🎭", role_taken: "🎭", privilege_good: "👑", privilege_declined: "👑",
    settler_passed: "⏭️", builder_passed: "⏭️", captain_passed: "⏭️", trader_passed: "⏭️",
    plantation_taken: "🌱", hacienda_plantation: "🌱", quarry_taken: "⛏️", building_built: "🏗️",
    colonists_distributed: "👥", colonist_placed: "🧑‍🌾", colonist_picked_up: "🧍", university_colonist: "🎓", mayor_finished: "✅",
    goods_produced: "📦", factory_bonus: "🏭", prospector_bonus: "💰", good_sold: "💰",
    goods_shipped: "🚢", wharf_shipped: "⚓", goods_discarded: "🗑️",
  };
})();
