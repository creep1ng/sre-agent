// Midnight landing (#870). The markup is Spanish; English replaces the marked nodes.
const EN = {
  "title": "Midnight · Close the laptop",
  "description": "Midnight watches the signals you already have, remembers every incident and every deploy, and wakes you only when your decision changes the outcome. Open source, on your VPS.",
  "nav.promises": "Promises",
  "nav.integrations": "Integrations",
  "nav.language": "Language",
  "nav.console": '<span class="lg">Open the&nbsp;</span>console&nbsp;→',
  "hero.sky": "Seven nights of signals; only one, Friday at 02:47, woke you",
  "hero.title": "A thousand signals in a week. <em>One</em> was for you.",
  "hero.lead": "Midnight watches what you already have, remembers what happened and wakes you only when your decision changes the outcome.",
  "copy": "Copy",
  "copied": "Copied",
  "letter.title": "Your attention is the most expensive thing you have. We treat it <em>that way</em>.",
  "letter.p1": "If you keep one client’s shop, another’s API and a third one’s WordPress running on two or three VPS that nobody else watches, you do not have an on-call team. You have a phone on the nightstand that buzzes at every blip. And still, the day something really breaks, you find out from the client’s email.",
  "letter.p2": "You do not need another dashboard, or an agent with the production keys. You need to sleep knowing that, if something needs your judgement, you will get one message with what you need to decide.",
  "letter.p3": "That is why I am building Midnight. It listens to the signals you already have, remembers your incidents and what you did about them, and acts only through operations you approved beforehand, leaving a receipt for each one.",
  "letter.p4": "Almost everything that happens at night ends in doing nothing, remembering it and leaving you alone. That is not a flaw. It is the product.",
  "msg.label": "Midnight’s message on Telegram",
  "msg.time": "Sat 02:47",
  "msg.p1": 'Payments at <b>Tienda&nbsp;Ruiz</b> have been failing at <span class="nb">38&nbsp;%</span> since 02:31.',
  "msg.p2": 'Friday’s 19:12 deploy cut the provider timeout from <span class="nb">10&nbsp;s</span> to <span class="nb">1&nbsp;s</span>,<sup>1</sup> and at this hour the provider answers more slowly.<sup>2</sup> On 12 September you fixed it with a rollback.<sup>3</sup>',
  "msg.p3": "Shall I roll <b>checkout</b> back to v1.13?",
  "msg.n2": "2 grafana query",
  "msg.n3": "3 incident 12 Sep",
  "msg.yes": "Roll back to v1.13",
  "msg.evidence": "Evidence",
  "msg.later": "Tomorrow",
  "pr.title": "Seven promises you can <em>check</em>.",
  "pr.1.h": "Silence is <em>the default</em>.",
  "pr.1.p": "Every event ends ignored, remembered, in the morning digest or as an interruption. It interrupts you only if your decision changes the outcome.",
  "pr.1.no": "Alerts for blips that recover on their own.",
  "pr.1.ok": "One message per real incident. Zero in a week without failures.",
  "pr.2.h": "What is not in the catalog <em>cannot happen</em>.",
  "pr.2.p": "The agent calls named operations with typed data. Credentials live in a separate executor that verifies the signature of every call.",
  "pr.2.no": "A shell. Credentials inside the agent.",
  "pr.2.ok": "A hostile alert produces nothing outside the catalog.",
  "pr.3.h": "Every action is <em>accountable</em>.",
  "pr.3.p": "Every action leaves a receipt. An ambiguous result is never retried on its own. Every execution ends with a reason you can read.",
  "pr.3.no": "Hung executions. Restart loops.",
  "pr.3.ok": "We kill the gateway and the executor at every step: nothing runs twice.",
  "pr.4.h": "Memory <em>has a source</em>.",
  "pr.4.p": "It remembers your incidents, mitigations and deploys, each linked to its origin. It proposes changes; it never rewrites its own rules.",
  "pr.4.no": "Facts without a source. Prompts that modify themselves.",
  "pr.4.ok": "Every memory links to the record it comes from.",
  "pr.5.h": "The engine is the product.",
  "pr.5.p": "Everything exists in the API first. Chat, the console and other agents over MCP use the same engine.",
  "pr.5.no": "Features that exist only in our interface.",
  "pr.5.ok": "The demo runs end to end with the console closed.",
  "pr.6.h": "We claim only <em>what we measured</em>.",
  "pr.6.p": "Blind evaluations with a rubric fixed in advance, next to Claude Code, with the failed runs included.",
  "pr.6.no": "Alerts with hints from someone who knows the fault.",
  "pr.6.ok": "The report lists every run. The first one has not run yet.",
  "pr.7.h": "Pocket-sized <em>economics</em>.",
  "pr.7.p": "Under 1&nbsp;USD per user per month as a target. Rules and memory decide before a model is called.",
  "pr.7.no": "One model call per event.",
  "pr.7.ok": "Cost per investigation and per idle month, recorded.",
  "wiring.title": "It sits <em>between</em> your signals and you.",
  "wiring.label": "Grafana, Alertmanager, Uptime Kuma and GitHub Actions flow into Midnight; Midnight goes out through Telegram, the API, MCP and the console. Only Telegram carries interruptions.",
  "wiring.console": "Console",
  "closing.title": "Open the code.<br /><em>Close</em> the laptop.",
  "closing.github": "View on GitHub",
  "closing.console": "Open the console&nbsp;→",
  "footer": 'Open source. The week on the cover is simulated. What does not hold yet: <a href="https://github.com/creep1ng/sre-agent/issues/758">#758</a>, <a href="https://github.com/creep1ng/sre-agent/issues/760">#760</a>.',
  "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
};
const ES = { "copied": "Copiado", "days": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"] };
const STORAGE_KEY = "midnight.lang";
const description = document.querySelector('meta[name="description"]');
ES.title = document.title;
ES.description = description.content;
document.querySelectorAll("[data-i18n]").forEach((node) => { ES[node.dataset.i18n] = node.innerHTML; });
document.querySelectorAll("[data-i18n-aria]").forEach((node) => { ES[node.dataset.i18nAria] = node.getAttribute("aria-label"); });
let lang = "es";
let dayLabels = [];

function setLang(next) {
  lang = next;
  const words = next === "en" ? EN : ES;
  document.documentElement.lang = next;
  document.title = words.title;
  description.content = words.description;
  document.querySelectorAll("[data-i18n]").forEach((node) => { node.innerHTML = words[node.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => { node.setAttribute("aria-label", words[node.dataset.i18nAria]); });
  document.querySelectorAll("[data-lang]").forEach((button) => { button.setAttribute("aria-pressed", String(button.dataset.lang === next)); });
  dayLabels.forEach((label, i) => { label.textContent = words.days[i]; });
}

// Seven simulated nights. Friday is deploy night: it is the only one with an interrupt.
function rng(seed) { return () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296; }
function sky(id, seed, withStar) {
  const svg = document.getElementById(id), W = 1440, H = 920, NS = "http://www.w3.org/2000/svg";
  // On phones the sky frames Friday night alone, so the star stays in view.
  const narrow = withStar && matchMedia("(max-width: 900px)").matches;
  svg.setAttribute("viewBox", narrow ? `${W / 7 * 3.5} 280 ${W / 7 * 2} 460` : `0 0 ${W} ${H}`); svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  const r = rng(seed), el = (n, a) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); svg.appendChild(e); return e; };
  const top = 110, bottom = 690, colW = W / 7;
  for (let d = 0; d < 7; d++) {
    const x0 = d * colW, friday = d === 4;
    const n = (friday ? 230 : 120) + Math.floor(r() * 50);
    for (let i = 0; i < n; i++) {
      const t = friday && r() < .45 ? .1 + r() * .25 : (r() < .3 ? .35 + (r() - .5) * .12 : r());
      const x = x0 + colW / 2 + (r() - .5) * colW * .82 * Math.sqrt(r());
      const y = top + t * (bottom - top), p = r();
      if (p < .86) el("circle", { cx: x, cy: y, r: .7 + r() * 1.1, fill: "#6f7396", opacity: .25 + r() * .4 });
      else if (p < .975) el("circle", { cx: x, cy: y, r: 2 + r() * 1.2, fill: "none", stroke: "#a797d7", "stroke-width": .8, opacity: .55 });
      else el("circle", { cx: x, cy: y, r: 1.8, fill: "#e4d9ff", opacity: .85 });
    }
  }
  if (!withStar) return;
  const sx = colW * 4.5, sy = bottom - 70;
  const g = el("radialGradient", { id: id + "g" }); [[0, .65], [1, 0]].forEach(([o, a]) => { const s = document.createElementNS(NS, "stop"); s.setAttribute("offset", o); s.setAttribute("stop-color", "#f2b45a"); s.setAttribute("stop-opacity", a); g.appendChild(s); });
  el("circle", { cx: sx, cy: sy, r: 80, fill: `url(#${id}g)` });
  el("rect", { x: sx - 7, y: sy - 7, width: 14, height: 14, fill: "#f2b45a" });
  const t = el("text", { x: sx + 22, y: sy + 5, fill: "#f2b45a", "font-family": "JetBrains Mono, monospace", "font-size": 15, "font-weight": 500 }); t.textContent = "02:47";
  dayLabels = ES.days.map((d, i) => {
    const l = el("text", { x: i * colW + colW / 2, y: bottom + 50, fill: i === 4 ? "#f2b45a" : "#6f7396", "text-anchor": "middle", "font-family": "JetBrains Mono, monospace", "font-size": 13 }); l.textContent = d; return l;
  });
}
sky("sky", 20261030, true);
sky("sky2", 7, false);

// The stored choice wins; otherwise English only for browsers that ask for it.
const stored = localStorage.getItem(STORAGE_KEY);
setLang(stored === "en" || stored === "es" ? stored : (navigator.language || "").toLowerCase().startsWith("en") ? "en" : "es");
document.querySelectorAll("[data-lang]").forEach((button) => button.addEventListener("click", () => {
  localStorage.setItem(STORAGE_KEY, button.dataset.lang);
  setLang(button.dataset.lang);
}));
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  // The clipboard exists only on secure origins; say "copied" only when it really copied.
  navigator.clipboard?.writeText("git clone https://github.com/creep1ng/sre-agent && cd sre-agent && docker compose up -d")
    .then(() => { button.textContent = (lang === "en" ? EN : ES).copied; });
});
