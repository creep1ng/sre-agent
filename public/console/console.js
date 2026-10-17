import { DEFAULT_VIEW, DOMAINS, hrefFor, routeFrom, viewById, viewForPath } from "./routes.js";
import { createTabSession } from "./session.js";
import { mountView } from "./view.js";

const session = createTabSession();
const byId = (id) => document.getElementById(id);
const host = byId("console-view");
const live = byId("console-live");
const domainCrumb = byId("console-domain");
const surfaceCrumb = byId("console-surface");
const sessionPanel = byId("console-session");
const sessionForm = byId("session-form");
const apiKeyInput = byId("api-key");
const connectButton = byId("connect-button");
const sessionMessage = byId("session-message");
const retryButton = byId("session-retry");
const cancelButton = byId("session-cancel");
const chip = byId("session-chip");
const chipPrincipal = byId("session-principal");
const chipState = byId("session-state");
const menu = byId("session-menu");
const changeButton = byId("change-credential");
const disconnectButton = byId("disconnect-button");

const PHASE_LABELS = Object.freeze({
  anonymous: { identity: "Sin sesión", detail: "Conectar credencial" },
  validating: { identity: "Validando…", detail: "Comprobando con la API" },
  active: { identity: null, detail: "Sesión activa" },
});

const REASON_MESSAGES = Object.freeze({
  invalid_credential: "La API rechazó esa credencial. Revisa la API key e inténtalo de nuevo.",
  credential_rejected: "La sesión terminó porque la API rechazó la credencial. Conéctate de nuevo.",
  logout: "Sesión cerrada. Todas las vistas descartaron sus datos.",
  network: "No se pudo contactar la API para validar la credencial.",
});

// The route table decides where each entry opens while surfaces move into the console.
for (const link of document.querySelectorAll("[data-console-nav]")) {
  link.href = hrefFor(link.dataset.consoleNav);
}

let active = null;
let renderId = 0;
let renderChain = Promise.resolve();
let changingCredential = false;

function announce(message) {
  live.textContent = "";
  live.textContent = message;
}

function navigate(viewId, params = {}, { replace = false } = {}) {
  const href = hrefFor(viewId, params);
  if (viewById(viewId)?.legacy) {
    location.assign(href);
    return;
  }
  history[replace ? "replaceState" : "pushState"](null, "", href);
  render({ focus: true });
}

// Lets a view keep its own read selection (a run, a filter) in the address without remounting.
function replaceParams(next) {
  const url = new URL(location.href);
  for (const [key, value] of Object.entries(next)) {
    if (value === undefined || value === null || value === "") url.searchParams.delete(key);
    else url.searchParams.set(key, String(value));
  }
  history.replaceState(null, "", url);
}

function markLocation(viewId, view) {
  const current = view?.nav ?? viewId;
  for (const link of document.querySelectorAll("[data-console-nav]")) {
    if (link.dataset.consoleNav === current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const label = view?.label ?? "Vista no encontrada";
  domainCrumb.textContent = view ? DOMAINS[view.domain] : "Consola";
  surfaceCrumb.textContent = label;
  document.title = `${label} · midnight.agent`;
}

function emptyState(title, detail, action) {
  const region = document.createElement("section");
  region.className = "ma-empty-state console-empty";
  const heading = document.createElement("h1");
  heading.className = "ma-empty-state__title";
  heading.textContent = title;
  const text = document.createElement("p");
  text.className = "ma-empty-state__detail";
  text.textContent = detail;
  region.append(heading, text);
  if (action) region.append(action);
  return region;
}

function homeLink() {
  const link = document.createElement("a");
  link.className = "ma-button ma-button--secondary";
  link.href = hrefFor(DEFAULT_VIEW);
  link.textContent = "Ir a Alertas";
  return link;
}

function focusView() {
  const heading = host.querySelector("h1") ?? host.querySelector("h2");
  const target = heading ?? byId("console-content");
  if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: false });
}

async function renderNow(id, { focus }) {
  if (id !== renderId) return;
  const { viewId, view, params } = routeFrom(location);
  active?.unmount();
  active = null;
  markLocation(viewId, view);
  syncSession(session.state);

  if (!view || view.legacy) {
    host.replaceChildren(
      emptyState(
        "Vista no encontrada",
        `La consola no tiene una vista llamada «${viewId}». Usa la navegación para continuar.`,
        homeLink(),
      ),
    );
    if (focus) focusView();
    return;
  }

  host.setAttribute("aria-busy", "true");
  try {
    const mounted = await mountView({ host, viewId, view, params, session, navigate, replaceParams });
    if (id !== renderId) {
      mounted.unmount();
      return;
    }
    active = mounted;
    if (focus) focusView();
    announce(`${view.label} abierta.`);
  } catch (error) {
    if (id !== renderId) return;
    console.error(error);
    host.replaceChildren(
      emptyState(
        "No se pudo abrir la vista",
        `${view.label} no cargó. Recarga la página o vuelve a intentarlo en unos segundos.`,
        homeLink(),
      ),
    );
  } finally {
    if (id === renderId) host.removeAttribute("aria-busy");
  }
}

function render({ focus = false } = {}) {
  const id = ++renderId;
  renderChain = renderChain.then(() => renderNow(id, { focus }));
  return renderChain;
}

function setMenu(open) {
  menu.hidden = !open;
  chip.setAttribute("aria-expanded", String(open));
}

function syncSession(state) {
  const view = routeFrom(location).view;
  const needsSession = Boolean(view && !view.legacy && view.session !== false);
  // Views that read the API ask for the key; any view keeps showing a validation in progress or
  // a rejected key, so the person can act on it.
  const pendingAttention =
    state.phase === "validating" || ["invalid_credential", "credential_rejected"].includes(state.reason);
  const showPanel = changingCredential || (state.phase !== "active" && (needsSession || pendingAttention));

  const labels = PHASE_LABELS[state.phase] ?? PHASE_LABELS.anonymous;
  chip.dataset.phase = state.phase;
  chipPrincipal.textContent = state.principalId ?? labels.identity;
  chipState.textContent = labels.detail;
  if (state.phase !== "active") setMenu(false);

  sessionPanel.hidden = !showPanel;
  sessionPanel.dataset.phase = state.phase;
  const validating = state.phase === "validating";
  apiKeyInput.disabled = validating && !state.reason;
  connectButton.disabled = validating && !state.reason;
  retryButton.hidden = !(validating && state.reason);
  cancelButton.hidden = !(changingCredential && state.phase === "active");

  let message = REASON_MESSAGES[state.reason] ?? "";
  if (validating) {
    message = state.reason
      ? REASON_MESSAGES[state.reason] ?? "La API no pudo validar la credencial en este momento."
      : "Validando la credencial con la API…";
  } else if (state.phase === "active") {
    message = changingCredential ? `Sesión activa como ${state.principalId}. La nueva key la reemplaza en todas las vistas.` : "";
  }
  sessionMessage.textContent = message;
  sessionMessage.dataset.tone = ["invalid_credential", "credential_rejected"].includes(state.reason) || (validating && state.reason) ? "critical" : "info";
}

sessionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = apiKeyInput.value.trim();
  apiKeyInput.value = "";
  if (!value) {
    sessionMessage.textContent = "Escribe una API key para conectar la consola.";
    sessionMessage.dataset.tone = "critical";
    apiKeyInput.focus();
    return;
  }
  try {
    changingCredential = false;
    session.setCredential(value);
  } catch {
    sessionMessage.textContent = "La API key solo admite caracteres visibles, sin espacios.";
    sessionMessage.dataset.tone = "critical";
    apiKeyInput.focus();
  }
});

retryButton.addEventListener("click", () => session.retry());

cancelButton.addEventListener("click", () => {
  changingCredential = false;
  syncSession(session.state);
  chip.focus();
});

chip.addEventListener("click", () => {
  if (session.state.phase === "active") {
    setMenu(menu.hidden);
    return;
  }
  changingCredential = true;
  syncSession(session.state);
  apiKeyInput.focus();
});

changeButton.addEventListener("click", () => {
  setMenu(false);
  changingCredential = true;
  syncSession(session.state);
  apiKeyInput.focus();
});

disconnectButton.addEventListener("click", () => {
  setMenu(false);
  changingCredential = false;
  session.logout();
  chip.focus();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !menu.hidden) {
    setMenu(false);
    chip.focus();
  }
});

document.addEventListener("click", (event) => {
  if (!menu.hidden && !menu.contains(event.target) && !chip.contains(event.target)) setMenu(false);
});

session.subscribe((state) => {
  syncSession(state);
  if (state.phase === "active") announce(`Sesión activa como ${state.principalId}.`);
  else if (state.reason && REASON_MESSAGES[state.reason]) announce(REASON_MESSAGES[state.reason]);
});

// Same-origin links to console views, including the old page addresses of surfaces that moved
// into the console, stay inside this document so the session and the context survive.
document.addEventListener("click", (event) => {
  if (event.defaultPrevented || event.button !== 0) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest?.("a[href]");
  if (!link || (link.target && link.target !== "_self") || link.hasAttribute("download")) return;
  const url = new URL(link.href, location.href);
  if (url.origin !== location.origin) return;
  if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
  const atRoot = url.pathname === "/" || url.pathname === "/index.html";
  const viewId = atRoot ? url.searchParams.get("view") ?? DEFAULT_VIEW : viewForPath(url.pathname);
  if (!viewId || (!atRoot && viewById(viewId)?.legacy)) return;
  event.preventDefault();
  url.searchParams.delete("view");
  navigate(viewId, Object.fromEntries(url.searchParams));
});

window.addEventListener("popstate", () => render({ focus: true }));

render();
