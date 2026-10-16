import { ApiClientError } from "/public/api/client.js";
import {
  ACTORS,
  EVENT_KINDS,
  RUN_LABELS,
  STATE_DESCRIPTIONS,
  stateLabel,
} from "/public/console/incident-vocabulary.js";
import { mountedView } from "/public/console/view.js";

const view = mountedView();
const TIMELINE_LIMIT = 50;

const SVG = "http://www.w3.org/2000/svg";
const clockFormat = new Intl.DateTimeFormat("es-CO", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
const dayFormat = new Intl.DateTimeFormat("es-CO", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const shortDayFormat = new Intl.DateTimeFormat("es-CO", {
  weekday: "short",
  day: "numeric",
  month: "short",
});

const state = {
  incidentId: null,
  incidentState: null,
  runId: null,
  selectedRunId: null,
  cursor: null,
  hasMore: false,
  eventCount: 0,
  // Posición de lectura del timeline pintado: el primer instante del run, el último estado
  // alcanzado y el último día local mostrado. «Cargar más» sigue desde ahí; otro run empieza de cero.
  startedAt: null,
  lastState: null,
  lastDay: null,
  version: null,
  generation: 0,
};

const nodes = {};
const client = view.client;

function byId(id) {
  return document.getElementById(id);
}

function cacheNodes() {
  [
    "war-room",
    "loading-state",
    "error-missing-id",
    "error-401",
    "error-403",
    "error-404",
    "error-503",
    "summary-section",
    "fact-impact",
    "fact-snapshot",
    "fact-alert",
    "approvals-empty",
    "approvals-list",
    "timeline-section",
    "timeline-count",
    "timeline-context",
    "run-select",
    "run-current",
    "timeline-list",
    "timeline-empty",
    "load-more",
    "refresh-button",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function formatTimestamp(timestamp) {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }

  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
    hour12: false,
  }).format(parsed);
}

function hideAll() {
  [
    "loading-state",
    "error-missing-id",
    "error-401",
    "error-403",
    "error-404",
    "error-503",
    "summary-section",
    "timeline-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["refresh-button"].hidden = true;
}

function showError(kind, status) {
  hideAll();
  nodes[`error-${kind}`].hidden = false;
  nodes["war-room"].dataset.state = "error";
  // Toda vista de error conserva una vía de recuperación: reintentar con
  // Actualizar o, ante 401/403, cambiar la credencial desde la sesión de la consola.
  nodes["refresh-button"].hidden = false;
  view.focusIncident(null);
  console.error(`War room failed: HTTP ${status}`);
}

function newGeneration() {
  state.generation += 1;
  return state.generation;
}

function clearSessionData() {
  nodes["timeline-list"].replaceChildren();
  nodes["timeline-context"].textContent = "";
  nodes["load-more"].disabled = false;
  state.incidentState = null;
  state.runId = null;
  state.cursor = null;
  state.hasMore = false;
  state.eventCount = 0;
  state.startedAt = null;
  state.lastState = null;
  state.lastDay = null;
  state.version = null;
}

function latestRunId(detail) {
  const runs = Array.isArray(detail.runs) ? detail.runs : [];
  if (runs.length === 0) return null;
  const runId = runs[runs.length - 1].run_id;
  return typeof runId === "string" ? runId : null;
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function screenReaderText(content) {
  return element("span", "ma-sr-only", content);
}

function icon(name) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "ma-icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `/public/icons.svg#${name}`);
  svg.append(use);
  return svg;
}

function localDay(date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

// Desfase del reloj de quien lee en esa fecha, como «UTC−5» o «UTC+5:30».
function utcOffset(date) {
  const minutes = -date.getTimezoneOffset();
  const sign = minutes < 0 ? "−" : "+";
  const hours = Math.floor(Math.abs(minutes) / 60);
  const rest = Math.abs(minutes) % 60;
  return `UTC${sign}${hours}${rest ? `:${String(rest).padStart(2, "0")}` : ""}`;
}

// Tiempo desde el primer evento del run: «+45 s», «+1 min 30 s», «+2 h 5 min», «+1 d 3 h».
function formatOffset(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  if (seconds < 60) return `+${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `+${minutes} min${seconds % 60 ? ` ${seconds % 60} s` : ""}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `+${hours} h${minutes % 60 ? ` ${minutes % 60} min` : ""}`;
  return `+${Math.floor(hours / 24)} d${hours % 24 ? ` ${hours % 24} h` : ""}`;
}

// Hora local con segundos, el tiempo desde el primer evento y, cuando cambia el día, el día.
function timeCell(event) {
  const cell = element("div", "ma-timeline__time war-room__event-time");
  const occurred = new Date(event.occurred_at);
  if (Number.isNaN(occurred.getTime())) {
    cell.append(element("span", "", String(event.occurred_at ?? "—")));
    return cell;
  }
  const day = localDay(occurred);
  if (state.lastDay !== null && day !== state.lastDay) {
    cell.append(element("span", "war-room__event-day", shortDayFormat.format(occurred)));
  }
  state.lastDay = day;
  const time = element("time", "", clockFormat.format(occurred));
  time.dateTime = event.occurred_at;
  cell.append(time);
  if (state.startedAt === null) {
    state.startedAt = occurred.getTime();
    cell.append(element("span", "war-room__event-offset", "inicio"));
  } else {
    const offset = element(
      "span",
      "war-room__event-offset",
      formatOffset(occurred.getTime() - state.startedAt),
    );
    offset.append(screenReaderText(" desde el inicio"));
    cell.append(offset);
  }
  return cell;
}

function stateChip(stateId) {
  return element("span", "war-room__state", stateLabel(stateId));
}

// El estado que alcanzó el evento; un lector de pantalla lo lee «Estado: de En triage a Activo».
function transition(from, to) {
  const line = element("p", "war-room__event-state");
  if (from === null) {
    line.append("Empieza en ", stateChip(to));
  } else {
    line.append(
      screenReaderText("Estado: de "),
      stateChip(from),
      icon("icon-arrow-right"),
      screenReaderText(" a "),
      stateChip(to),
    );
  }
  return line;
}

function actorLine(actor) {
  const line = element("p", "war-room__event-actor");
  const type = actor && typeof actor === "object" ? actor.type : null;
  const known = ACTORS[type];
  line.append(
    icon(known?.icon ?? "icon-system"),
    element("strong", "", known?.label ?? (typeof type === "string" && type ? type : "Sistema")),
  );
  const reference = actor?.reference;
  if (reference && typeof reference.principal_id === "string") {
    const name = typeof reference.display_name === "string" ? reference.display_name.trim() : "";
    const principal = element("span", "ma-mono", reference.principal_id);
    if (name && name !== reference.principal_id) line.append(` · ${name} (`, principal, ")");
    else line.append(" · ", principal);
  }
  return line;
}

function eventItem(event, position) {
  const kind = EVENT_KINDS[event.kind];
  const tone = kind?.tone ?? "info";
  const item = element("li", "ma-timeline__item war-room__event");
  const marker = element("span", "ma-timeline__marker war-room__event-marker", String(position));
  marker.dataset.tone = tone;
  marker.setAttribute("aria-hidden", "true");

  const content = element("div", "ma-timeline__content");
  const head = element("div", "war-room__event-head");
  const title = element("h3", "ma-timeline__title", event.summary ?? "Evento registrado.");
  // El runtime escribe sus resúmenes en inglés; marcarlos hace que el lector de pantalla los
  // pronuncie bien.
  if (event.summary) title.lang = "en";
  const badge = element("span", "ma-badge", kind?.label ?? String(event.kind ?? "Evento"));
  badge.dataset.tone = tone;
  head.append(title, badge);
  content.append(head);

  const reached = typeof event.state === "string" && event.state !== "" ? event.state : null;
  if (reached !== null && reached !== state.lastState) {
    item.dataset.reached = reached;
    content.append(transition(state.lastState, reached));
    const meaning = STATE_DESCRIPTIONS[reached];
    if (meaning) content.append(element("p", "ma-timeline__detail", meaning));
  }
  if (reached !== null) state.lastState = reached;
  content.append(actorLine(event.actor));
  item.append(timeCell(event), marker, content);
  return item;
}

// «Estado actual» marca el último cambio de estado cuando el run está completo y ese estado es el
// actual del incidente; mientras queden páginas, el último estado del run aún no se conoce.
function markCurrentState() {
  const list = nodes["timeline-list"];
  list.querySelectorAll(".war-room__event-now").forEach((node) => node.remove());
  list.querySelectorAll(".war-room__state[data-current]").forEach((node) => {
    delete node.dataset.current;
  });
  if (state.hasMore) return;
  const changes = list.querySelectorAll(".war-room__event[data-reached]");
  const last = changes[changes.length - 1];
  if (!last || last.dataset.reached !== state.incidentState) return;
  const line = last.querySelector(".war-room__event-state");
  const chips = line.querySelectorAll(".war-room__state");
  chips[chips.length - 1].dataset.current = "";
  const now = element("span", "war-room__event-now");
  now.append(screenReaderText("· "), "Estado actual");
  line.append(now);
}

function timelineContext() {
  if (state.startedAt === null) return "";
  const started = new Date(state.startedAt);
  const day = dayFormat.format(started);
  return `Del más antiguo al más reciente · ${day} · hora local (${utcOffset(started)})`;
}

// Title, state, severity, identifiers and version head the view in the console's incident band.
function renderSummary(detail, snapshot) {
  nodes["fact-impact"].textContent = detail.impact ?? "—";
  if (snapshot) {
    nodes["fact-snapshot"].textContent =
      `v${snapshot.version} (seq ${snapshot.event_sequence})`;
  } else {
    nodes["fact-snapshot"].textContent = "Sin snapshot todavía";
  }
  const alert = detail.alert;
  if (alert !== null && typeof alert === "object") {
    nodes["fact-alert"].textContent =
      `${alert.service ?? "—"} · ${alert.severity ?? "—"} · ${alert.summary ?? "—"}`;
  } else {
    nodes["fact-alert"].textContent =
      "Declarado por triage sin contexto de alerta.";
  }

  nodes["approvals-list"].replaceChildren();
  const approvals = Array.isArray(detail.approvals) ? detail.approvals : [];
  nodes["approvals-empty"].hidden = approvals.length > 0;
  approvals.forEach((approval) => {
    const item = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "ma-badge";
    badge.dataset.tone = approval.granted ? "success" : "critical";
    badge.textContent = approval.granted ? "Aprobado" : "Rechazado";
    const text = document.createElement("span");
    text.textContent = `${approval.subject_id} · ${formatTimestamp(approval.decided_at)}`;
    item.append(badge, text);
    nodes["approvals-list"].append(item);
  });

  nodes["summary-section"].hidden = false;
}

function renderEvents(events, { append } = {}) {
  if (!append) {
    nodes["timeline-list"].replaceChildren();
    state.eventCount = 0;
    state.startedAt = null;
    state.lastState = null;
    state.lastDay = null;
  }

  events.forEach((event) => {
    state.eventCount += 1;
    nodes["timeline-list"].append(eventItem(event, state.eventCount));
  });
  markCurrentState();

  nodes["timeline-empty"].hidden = state.eventCount > 0;
  nodes["timeline-count"].textContent =
    state.eventCount === 1 ? "1 evento" : `${state.eventCount} eventos`;
  nodes["timeline-context"].textContent = timelineContext();
  nodes["timeline-section"].hidden = false;
}

function runLabel(run) {
  const status =
    typeof run.status === "string" && run.status ? (RUN_LABELS[run.status] ?? run.status) : "—";
  return `${run.run_id} · ${status} · ${stateLabel(run.current_state)}`;
}

function resolveRunId(detail) {
  const runs = Array.isArray(detail.runs) ? detail.runs : [];
  const ids = runs.map((run) => run.run_id);
  if (state.selectedRunId !== null && ids.includes(state.selectedRunId)) {
    return state.selectedRunId;
  }
  return latestRunId(detail);
}

function renderRunPicker(detail, activeRunId) {
  const runs = Array.isArray(detail.runs) ? detail.runs : [];
  const select = nodes["run-select"];
  select.replaceChildren();
  runs.forEach((run) => {
    if (!run || typeof run.run_id !== "string") return;
    const option = document.createElement("option");
    option.value = run.run_id;
    option.textContent = runLabel(run);
    select.append(option);
  });
  if (activeRunId !== null) {
    select.value = activeRunId;
    nodes["run-current"].textContent = `Timeline del run ${activeRunId}.`;
  } else {
    nodes["run-current"].textContent = "";
  }
}

async function fetchTimeline({ runId, after } = {}) {
  return client.getIncidentTimeline(state.incidentId, {
    runId,
    after,
    limit: TIMELINE_LIMIT,
  });
}

async function loadAll() {
  const generation = newGeneration();
  const keptSelection = state.selectedRunId;
  clearSessionData();
  state.selectedRunId = keptSelection;
  hideAll();
  nodes["loading-state"].hidden = false;
  nodes["war-room"].dataset.state = "loading";

  try {
    const detail = await client.getIncident(state.incidentId);
    // El run activo es una referencia autoritativa: la elección explícita se
    // conserva entre recargas mientras siga existiendo; sin elección se sigue
    // el último run y el cursor seq:N nunca mezcla runs.
    if (generation !== state.generation) return;
    const runId = resolveRunId(detail);
    renderRunPicker(detail, runId);
    // El run leído queda en la dirección para que el recorrido y la recarga lo conserven.
    view.replaceParams({ run_id: runId });
    let timeline;
    try {
      timeline = await fetchTimeline({ runId });
    } catch (error) {
      if (!(error instanceof ApiClientError) || error.code !== "run_absent") throw error;
      // Incidente sin runs: timeline explícitamente vacío, no es un error.
      timeline = { events: [], next_cursor: "seq:-1", has_more: false };
    }
    let snapshot = null;
    try {
      snapshot = await client.getIncidentSnapshot(state.incidentId, { runId });
    } catch (error) {
      if (!(error instanceof ApiClientError) || error.status !== 404) throw error;
      // Ausencia explícita de snapshot: se muestra sin snapshot, no es fatal.
    }

    if (generation !== state.generation) return;
    state.runId = runId;
    state.cursor = timeline.next_cursor;
    state.hasMore = timeline.has_more === true;
    state.version = detail.version;
    state.incidentState = typeof detail.state === "string" ? detail.state : null;
    renderSummary(detail, snapshot);
    renderEvents(timeline.events ?? []);
    view.focusIncident(detail, runId);
    nodes["load-more"].hidden = !state.hasMore;
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
    nodes["war-room"].dataset.state = "ready";
  } catch (error) {
    if (generation !== state.generation) return;
    if (error instanceof ApiClientError) {
      if (error.kind === "authentication") showError("401", error.status);
      else if (error.kind === "authorization") showError("403", error.status);
      else if (error.kind === "conflict") showError("503", error.status);
      else if (error.status === 404) showError("404", error.status);
      else showError("503", error.status ?? "desconocido");
    } else {
      showError("503", "desconocido");
    }
  }
}

async function loadMore() {
  const generation = state.generation;
  nodes["load-more"].disabled = true;
  try {
    const page = await fetchTimeline({ runId: state.runId, after: state.cursor });
    // Una respuesta de una sesión/carga anterior nunca muta la vista actual.
    if (generation !== state.generation) return;
    state.cursor = page.next_cursor;
    state.hasMore = page.has_more === true;
    renderEvents(page.events ?? [], { append: true });
    nodes["load-more"].hidden = !state.hasMore;
  } catch (error) {
    if (generation !== state.generation) return;
    if (error instanceof ApiClientError) {
      // Tras una denegación no queda contenido protegido visible.
      if (error.kind === "authentication") showError("401", error.status);
      else if (error.kind === "authorization") showError("403", error.status);
      else showError("503", error.status ?? "desconocido");
    } else {
      showError("503", "desconocido");
    }
  } finally {
    if (generation === state.generation) nodes["load-more"].disabled = false;
  }
}

function selectRun(event) {
  const runId = event.target.value;
  if (!runId || runId === state.runId) return;
  state.selectedRunId = runId;
  loadAll();
}

// La credencial vive en la sesión de la consola: una sesión activa carga el incidente y
// cualquier cambio descarta lo leído con la credencial anterior.
function applySession(session) {
  if (session.phase === "active") {
    loadAll();
    return;
  }
  newGeneration();
  clearSessionData();
  hideAll();
  nodes["error-401"].hidden = false;
  nodes["war-room"].dataset.state = "auth";
}

cacheNodes();
nodes["refresh-button"].addEventListener("click", loadAll);
nodes["run-select"].addEventListener("change", selectRun);
nodes["load-more"].addEventListener("click", loadMore);

const incidentId = view.params.get("incident_id");
if (!incidentId) {
  hideAll();
  nodes["error-missing-id"].hidden = false;
  nodes["war-room"].dataset.state = "error";
} else {
  state.incidentId = incidentId;
  state.selectedRunId = view.params.get("run_id");
  view.onSession(applySession);
}
