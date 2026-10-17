import { ApiClientError } from "/public/api/client.js";
import { mountedView } from "/public/console/view.js";

const view = mountedView();
const TIMELINE_LIMIT = 50;

const eventKindTones = Object.freeze({
  denial: "critical",
  escalation: "critical",
  human_command: "warning",
  mitigation_proposed: "warning",
  run_terminated: "success",
});

const state = {
  incidentId: null,
  runId: null,
  selectedRunId: null,
  cursor: null,
  hasMore: false,
  eventCount: 0,
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
  nodes["load-more"].disabled = false;
  state.runId = null;
  state.cursor = null;
  state.hasMore = false;
  state.eventCount = 0;
  state.version = null;
}

function latestRunId(detail) {
  const runs = Array.isArray(detail.runs) ? detail.runs : [];
  if (runs.length === 0) return null;
  const runId = runs[runs.length - 1].run_id;
  return typeof runId === "string" ? runId : null;
}

function actorLabel(actor) {
  if (!actor || typeof actor !== "object") return "sistema";
  const reference = actor.reference;
  if (reference && typeof reference.principal_id === "string") {
    return `${actor.type} · ${reference.principal_id}`;
  }
  return String(actor.type ?? "sistema");
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
  }

  events.forEach((event) => {
    const item = document.createElement("li");
    item.className = "war-room__event";
    const badge = document.createElement("span");
    badge.className = "ma-badge";
    badge.dataset.tone = eventKindTones[event.kind] ?? "info";
    badge.textContent = event.kind;
    const summary = document.createElement("strong");
    summary.textContent = event.summary ?? "Evento registrado.";
    const meta = document.createElement("span");
    meta.className = "war-room__event-meta";
    const eventState = typeof event.state === "string" && event.state ? event.state : "—";
    meta.textContent =
      `${actorLabel(event.actor)} · ${formatTimestamp(event.occurred_at)} · seq ${event.sequence} · estado ${eventState}`;
    item.append(badge, summary, meta);
    nodes["timeline-list"].append(item);
    state.eventCount += 1;
  });

  nodes["timeline-empty"].hidden = state.eventCount > 0;
  nodes["timeline-count"].textContent =
    state.eventCount === 1 ? "1 evento" : `${state.eventCount} eventos`;
  nodes["timeline-section"].hidden = false;
}

function runLabel(run) {
  const status = typeof run.status === "string" && run.status ? run.status : "—";
  const current =
    typeof run.current_state === "string" && run.current_state ? run.current_state : "—";
  return `${run.run_id} · ${status} · ${current}`;
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
