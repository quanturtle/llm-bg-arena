// New match page: pick an example or write a match config in YAML, then start it.
(function () {
  const { h, api, setActiveNav, showError, routes } = window.viewer;

  async function post(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
    return data;
  }

  function launchRow(launch) {
    const link = h("a", { href: `#/match/${launch.match_id}` }, launch.match_id);
    const badge = h("span", { class: `badge ${launch.status}` }, launch.status);
    return h("li", {}, link, " ", badge, launch.error ? h("span", { class: "error" }, ` ${launch.error}`) : null);
  }

  async function renderNew() {
    setActiveNav("new");
    const [examples, launches] = await Promise.all([api("/api/examples"), api("/api/launches")]);
    const editor = h("textarea", { class: "config", rows: 18, spellcheck: "false", placeholder: "game: k_in_a_row\nseed: 7\n" });
    const picker = h("select", { onchange: (event) => { const chosen = examples.find((e) => e.name === event.target.value); if (chosen) editor.value = chosen.text; } },
      h("option", { value: "" }, "Start from an example…"),
      examples.map((e) => h("option", { value: e.name }, e.name)));
    const message = h("p", { class: "error" });
    const start = h("button", { class: "primary", onclick: async () => {
      message.textContent = "";
      start.disabled = true;
      try {
        const launch = await post("/api/matches", { yaml: editor.value });
        location.hash = `#/match/${launch.match_id}`;
      } catch (error) {
        message.textContent = error.message;
        start.disabled = false;
      }
    } }, "Start match");
    if (examples.length) editor.value = examples[0].text;
    return h("section", { class: "new-match" },
      h("h1", {}, "New match"),
      h("p", { class: "muted" }, "The config names the game, its settings and who sits at each seat. Language model seats need the server's OpenRouter key."),
      h("div", { class: "toolbar" }, picker, start),
      editor,
      message,
      launches.length ? h("div", {}, h("h2", {}, "Started from here"), h("ul", {}, launches.map(launchRow))) : null);
  }

  routes.new = renderNew;
})();
