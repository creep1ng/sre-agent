import { ApiClientError } from "/public/api/client.js";
import {
  ACTORS,
  EVENT_KINDS,
  RUN_LABELS,
  STATE_DESCRIPTIONS,
  stateLabel,
} from "/public/console/incident-vocabulary.js";
import {
  evidenceItem,
  hypothesisBlock,
  readReasoning,
} from "/public/console/incident-reasoning.js";
import { hrefFor } from "/public/console/routes.js";
import { mountedView } from "/public/console/view.js";

const view = mountedView();
const TIMELINE_LIMIT = 50;

const OBJECTIVE = "investigate";
const WORKFLOW_VERSION = "1.0.0";
const START_KEY_STORAGE = "midnight-agent-run-start";
// While the agent investigates (the start request in flight, or the run running in
// `investigating`), the view polls the run every few seconds and reloads when it changes.
const LIVE_EVERY_MS = 4000;
const LIVE_FOR_MS = 6 * 60 * 1000;

const TERMINATION_REASONS = Object.freeze({
  completed: "Investigación completada.",
  max_steps: "Run terminado: se agotó el presupuesto de pasos del harness.",
  needs_human: "Run terminado: hace falta intervención humana.",
  invalid_output: "Run terminado: el harness entregó salidas inválidas.",
  upstream_unavailable: "Run terminado: el proveedor no responde.",
});

function randomHex(bytes) {
  const values = new Uint8Array(bytes);
  globalThis.crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
}

// La clave de idempotencia es una referencia opaca del par incidente/objetivo; no es la
// credencial (esa vive solo en la memoria de la consola). sessionStorage la conserva en
// esta pestaña —sobrevive a la recarga del flujo y nunca entra a la URL— mientras la
// apertura está en vuelo; tras el éxito se descarta para que una investigación futura
// no repita el run anterior. Sin storage disponible se acuña por intento y el botón
// deshabilitado sigue cubriendo el doble clic.
function storedRunKey(incidentId, { resume, clear } = {}) {
  const suffix = resume === undefined ? "" : `:resume:${resume}`;
  const storageKey = `${START_KEY_STORAGE}:${incidentId}${suffix}`;
  try {
    if (clear) {
      window.sessionStorage.removeItem(storageKey);
      return null;
    }
    const stored = window.sessionStorage.getItem(storageKey);
    if (typeof stored === "string" && stored.length >= 8) return stored;
    const minted = `run-${resume === undefined ? "start" : "resume"}-${incidentId}-${randomHex(16)}`;
    window.sessionStorage.setItem(storageKey, minted);
    return minted;
  } catch {
    return `run-${resume === undefined ? "start" : "resume"}-${incidentId}-${randomHex(16)}`;
  }
}

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
  // GET /runs/{run_id} del run en foco, para la franja de la investigación.
  runState: null,
  // Posición de lectura del timeline pintado: el primer instante del run, el último estado
  // alcanzado y el último día local mostrado. «Cargar más» sigue desde ahí; otro run empieza de cero.
  startedAt: null,
  lastState: null,
  lastDay: null,
  version: null,
  generation: 0,
  // Bumped on every session change: an answer from an earlier session never lands in this one.
  session: 0,
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
    "error-409",
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
    "run-state",
    "run-status-line",
    "run-pending",
    "run-terminated",
    "run-decide",
    "run-start",
    "run-resume",
    "timeline-list",
    "timeline-empty",
    "load-more",
    "refresh-button",
    "reasoning-section",
    "reasoning-live",
    "reasoning-forbidden",
    "reasoning-unavailable",
    "reasoning-empty",
    "hypothesis-block",
    "hypothesis-content",
    "evidence-block",
    "evidence-title",
    "evidence-list",
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
    "error-409",
    "error-503",
    "summary-section",
    "reasoning-section",
    "timeline-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["refresh-button"].hidden = true;
  nodes["run-start"].hidden = true;
  nodes["run-resume"].hidden = true;
  nodes["run-state"].hidden = true;
}

function showError(kind, status) {
  stopLive();
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
  stopLive();
  renderReasoning(null);
  nodes["reasoning-live"].textContent = "";
  nodes["timeline-list"].replaceChildren();
  nodes["timeline-context"].textContent = "";
  nodes["load-more"].disabled = false;
  state.incidentState = null;
  state.runId = null;
  state.cursor = null;
  state.hasMore = false;
  state.eventCount = 0;
  state.runState = null;
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

// Franja del run en foco: estado proyectado, comando pendiente y motivo de
// terminación. `denied` nunca es terminado, completado ni exitoso.
// After the mitigation decision the run waits for no command: the war room points to the
// journey's next step (workflow 1.0.0), keyed by the incident's state.
const NEXT_STEPS = Object.freeze({
  verifying: Object.freeze({
    view: "decisions",
    label: "Ir a Decisiones",
    text: "La mitigación quedó aprobada: confirma en Decisiones si el servicio quedó estable.",
  }),
  resolved: Object.freeze({
    view: "postmortem",
    label: "Ir al postmortem",
    text: "El servicio quedó verificado: abre el postmortem y redáctalo.",
  }),
  postmortem: Object.freeze({
    view: "postmortem",
    label: "Ir al postmortem",
    text: "El postmortem está abierto: complétalo y revísalo; el cierre se confirma en Decisiones.",
  }),
});

function renderRunState(runState) {
  state.runState = runState;
  if (!runState || runState.run_id !== state.runId) {
    nodes["run-state"].hidden = true;
    nodes["run-resume"].hidden = true;
    return;
  }
  const status = typeof runState.status === "string" ? runState.status : null;
  const statusLabel = RUN_LABELS[status] ?? status ?? "—";
  if (runState.terminated_reason === "denied") {
    nodes["run-status-line"].textContent =
      `${state.runId} · Autorización denegada, requiere intervención.`;
  } else {
    nodes["run-status-line"].textContent =
      `${state.runId} · ${statusLabel} · ${stateLabel(runState.current_state)}`;
  }
  const pending =
    status === "awaiting_human" &&
    typeof runState.pending_command === "string" &&
    runState.pending_command !== ""
      ? runState.pending_command
      : null;
  // Una mitigación propuesta se decide en Decisiones; reanudar el run no la mueve.
  const deciding = status === "awaiting_human" && runState.current_state === "mitigating";
  const next = deciding ? null : (NEXT_STEPS[state.incidentState] ?? null);
  nodes["run-pending"].textContent = deciding
    ? "La investigación propuso una mitigación que espera tu decisión."
    : next !== null ? next.text : pending === null ? "" : `El run espera un comando: ${pending}.`;
  nodes["run-pending"].hidden = !deciding && next === null && pending === null;
  const target = next?.view ?? "decisions";
  nodes["run-decide"].href = hrefFor(target, { incident_id: state.incidentId, run_id: state.runId });
  nodes["run-decide"].textContent = next?.label ?? "Ir a Decisiones";
  nodes["run-decide"].hidden = !deciding && next === null;
  const reason = runState.terminated_reason;
  if (typeof reason === "string" && reason !== "" && reason !== "denied") {
    nodes["run-terminated"].textContent = TERMINATION_REASONS[reason] ?? `Run terminado (${reason}).`;
    nodes["run-terminated"].dataset.tone = reason === "completed" ? "success" : "warning";
    nodes["run-terminated"].hidden = false;
  } else {
    nodes["run-terminated"].hidden = true;
  }
  // Resuming only reads the run again: a run blocked by a denial needs a grant and a human, not a reread.
  nodes["run-resume"].hidden = status !== "awaiting_human" || deciding || runState.terminated_reason === "denied";
  nodes["run-state"].hidden = false;
}

// What the incident recorded from the investigation, only for run.read_context readers (the
// mitigation is read and decided in Decisiones). A refusal or a failed read is its own state
// inside the panel; the rest of the view stands.
function renderReasoning(result) {
  [
    "reasoning-forbidden", "reasoning-unavailable", "reasoning-empty",
    "hypothesis-block", "evidence-block",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  ["hypothesis-content", "evidence-list"].forEach((id) => {
    nodes[id].replaceChildren();
  });
  nodes["reasoning-section"].hidden = result === null;
  if (result === null) return;
  if (result.kind !== "ok") {
    nodes[result.kind === "forbidden" ? "reasoning-forbidden" : "reasoning-unavailable"].hidden = false;
    return;
  }
  const hypotheses = result.reasoning.hypotheses.filter((item) => item && typeof item === "object");
  const evidence = result.reasoning.evidence.filter((item) => item && typeof item === "object");
  let cited = new Set();
  if (hypotheses.length === 0) {
    nodes["reasoning-empty"].hidden = false;
  } else {
    const { block, current } = hypothesisBlock(hypotheses);
    cited = new Set(Array.isArray(current.supporting_evidence) ? current.supporting_evidence : []);
    nodes["hypothesis-content"].append(block);
    nodes["hypothesis-block"].hidden = false;
  }
  evidence.forEach((item) => nodes["evidence-list"].append(evidenceItem(item, cited)));
  nodes["evidence-title"].textContent = `Evidencia recolectada (${evidence.length})`;
  nodes["evidence-block"].hidden = evidence.length === 0;
}

let runActionInFlight = false;
const live = { timer: null, since: 0 };

function investigating(runState) {
  return runState?.status === "running" && runState?.current_state === "investigating";
}

function stopLive() {
  if (live.timer !== null) clearTimeout(live.timer);
  live.timer = null;
}

// The run line heads the panel; while the agent works it says so and when it last checked.
function showLive(runId, runState) {
  const active = runActionInFlight || investigating(runState);
  if (!active && runId === null) return;
  const status = RUN_LABELS[runState?.status] ?? runState?.status ?? "—";
  const line =
    runId === null ? "Iniciando la investigación…" : `${runId} · ${status} · ${stateLabel(runState?.current_state)}`;
  const activity = runActionInFlight ? "el agente está investigando" : "investigación en curso";
  nodes["reasoning-live"].textContent = active
    ? `${line} · ${activity}; la vista se actualiza sola (${clockFormat.format(new Date())}).`
    : line;
  if (active) nodes["reasoning-section"].hidden = false;
}

function scheduleLive(fresh) {
  stopLive();
  if (!runActionInFlight && !investigating(state.runState)) return;
  if (fresh) live.since = Date.now();
  if (Date.now() - live.since > LIVE_FOR_MS) {
    nodes["reasoning-live"].textContent += " Actualización automática detenida: usa Actualizar.";
    return;
  }
  const generation = state.generation;
  live.timer = setTimeout(() => liveTick(generation), LIVE_EVERY_MS);
}

// A start request in flight owns the reload when it answers; meanwhile only the line moves.
async function liveTick(generation) {
  live.timer = null;
  if (generation !== state.generation) return;
  try {
    let runId = state.runId;
    if (runActionInFlight || runId === null) runId = latestRunId(await client.getIncident(state.incidentId));
    const runState = runId === null ? null : await client.getRun(state.incidentId, runId);
    if (generation !== state.generation) return;
    const known = state.runState;
    const changed =
      runId !== state.runId ||
      runState?.cursor !== known?.cursor ||
      runState?.status !== known?.status ||
      runState?.current_state !== known?.current_state;
    if (changed && !runActionInFlight) {
      loadAll();
      return;
    }
    showLive(runId, runState);
  } catch {
    if (generation !== state.generation) return;
  }
  scheduleLive(false);
}

function showRunActionError(error) {
  if (!(error instanceof ApiClientError)) {
    showError("503", "desconocido");
    return;
  }
  if (error.kind === "authentication") showError("401", error.status);
  else if (error.kind === "authorization") showError("403", error.status);
  else if (error.kind === "not_found") showError("404", error.status);
  else if (error.status === 409) showError("409", error.status);
  else showError("503", error.status ?? "desconocido");
}

// La clave del intento es estable: un doble clic o un reintento reenvía el mismo
// POST y el servidor responde con el mismo run (200) en vez de crear otro. El
// resultado de una acción que quedó obsoleta se descarta.
async function beginRun(resumeRunId = null) {
  if (runActionInFlight) return;
  const resume = resumeRunId !== null && resumeRunId !== undefined;
  if (resume && resumeRunId !== state.runId) return;
  if (!resume && state.incidentState !== "active") return;
  runActionInFlight = true;
  nodes["run-start"].disabled = true;
  nodes["run-resume"].disabled = true;
  const generation = state.generation;
  const session = state.session;
  showLive(state.runId, resume ? state.runState : null);
  scheduleLive(true);
  const body = resume
    ? { workflow_version: WORKFLOW_VERSION, objective: OBJECTIVE, resume_from_run_id: resumeRunId }
    : { workflow_version: WORKFLOW_VERSION, objective: OBJECTIVE };
  try {
    const created = await client.startRun(
      state.incidentId,
      body,
      storedRunKey(state.incidentId, { resume: resume ? resumeRunId : undefined }),
    );
    // Another session discards the answer; a reload of this one (Actualizar) does not.
    if (session !== state.session) return;
    if (!resume) storedRunKey(state.incidentId, { clear: true });
    state.selectedRunId = created.run_id;
  } catch (error) {
    if (generation !== state.generation) return;
    showRunActionError(error);
    return;
  } finally {
    runActionInFlight = false;
    nodes["run-start"].disabled = false;
    nodes["run-resume"].disabled = false;
  }
  // A reload during the request read the run before it answered: read it again.
  loadAll();
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
    // La franja lee el run proyectado; un run que desaparece entre lecturas es
    // ausencia explícita, y el resto de faltas va al manejo de error global.
    let runState = null;
    if (runId !== null) {
      try {
        runState = await client.getRun(state.incidentId, runId);
      } catch (error) {
        if (!(error instanceof ApiClientError) || error.status !== 404) throw error;
      }
    }
    const reasoning = runId === null ? null : await readReasoning(client, state.incidentId, runId);

    if (generation !== state.generation) return;
    state.runId = runId;
    state.cursor = timeline.next_cursor;
    state.hasMore = timeline.has_more === true;
    state.version = detail.version;
    state.incidentState = typeof detail.state === "string" ? detail.state : null;
    renderSummary(detail, snapshot);
    renderEvents(timeline.events ?? []);
    view.focusIncident(detail, runId);
    renderRunState(runState);
    renderReasoning(reasoning);
    showLive(runId, runState);
    scheduleLive(true);
    nodes["run-start"].hidden = state.incidentState !== "active";
    nodes["run-start"].disabled = runActionInFlight;
    nodes["run-resume"].disabled = runActionInFlight;
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
  state.session += 1;
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
nodes["run-start"].addEventListener("click", () => beginRun());
nodes["run-resume"].addEventListener("click", () => beginRun(state.runId));

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
