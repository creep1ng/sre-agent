import { ApiClientError } from "/public/api/client.js";
import { stateLabel } from "/public/console/incident-vocabulary.js";
import { mountedView } from "/public/console/view.js";

// The persisted postmortem of the incident in focus (#43 over the #335 routes). The text arrives
// only for run.read_context; run.read alone reads the projection: version, review and runs.
const REVIEW_LABELS = Object.freeze({ pending: "Pendiente de revisión", approved: "Aprobada", changes_requested: "Cambios solicitados" });
const CERTAINTY_LABELS = Object.freeze({ confirmed: "Confirmada", probable: "Probable", hypothesis: "Hipótesis", unknown: "Desconocida" });
const SECTIONS = Object.freeze([
  ["summary", "Resumen"], ["impact", "Impacto conocido"], ["cause", "Causa o hipótesis"],
  ["strategy", "Estrategia"], ["timeline", "Cronología"], ["actions_taken", "Acciones realizadas"],
  ["verification", "Verificación"], ["pending", "Pendientes"], ["unknowns", "Lo que no se sabe"],
]);

const EMPTY_DETAILS = Object.freeze({
  resolved: "El incidente está resuelto: abrir el postmortem (start_postmortem) reserva su identificador.",
  postmortem: "El postmortem está abierto, sin contenido persistido todavía.",
});

const state = { incidentId: null, runId: null, generation: 0 };

const nodes = {};
const view = mountedView();
const client = view.client;

function byId(id) {
  return document.getElementById(id);
}

function cacheNodes() {
  [
    "postmortem", "loading-state", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section", "fact-incident",
    "fact-state", "fact-artifact", "fact-version", "fact-review", "fact-runs", "fact-updated",
    "artifact-section", "artifact-sections", "empty-section", "empty-detail", "content-restricted",
    "refresh-button",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function hideAll() {
  [
    "loading-state", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section", "artifact-section", "empty-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["artifact-sections"].replaceChildren();
  nodes["refresh-button"].hidden = true;
}

function showError(kind) {
  hideAll();
  nodes[`error-${kind}`].hidden = false;
  nodes["postmortem"].dataset.state = "error";
  nodes["refresh-button"].hidden = false;
  view.focusIncident(null);
}

function showKind(error) {
  if (!(error instanceof ApiClientError)) return "503";
  if (error.kind === "authentication") return "401";
  if (error.kind === "authorization") return "403";
  if (error.kind === "not_found") return "404";
  return "503";
}

function formatTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value ?? "—");
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short", hour12: false }).format(parsed);
}

// The run kept in focus: the one in the address, else the run in the incident's state, else the last.
function focusRun(detail) {
  const runs = (Array.isArray(detail.runs) ? detail.runs : []).filter((run) => typeof run?.run_id === "string");
  const chosen =
    runs.find((run) => run.run_id === state.runId) ??
    runs.find((run) => run.current_state === detail.state) ??
    runs[runs.length - 1];
  return chosen?.run_id ?? null;
}

function reviewText(review) {
  const label = REVIEW_LABELS[review?.status] ?? "—";
  if (!review?.reviewed_version) return label;
  const outcome = review.status === "pending" ? " (la última revisión es de otra versión)" : "";
  return `${label}${outcome} · versión ${review.reviewed_version} · ${review.reviewer_id ?? "—"} · ${formatTimestamp(review.reviewed_at)}`;
}

function sectionValue(key, value) {
  if (key === "cause") {
    return `${value?.statement ?? "—"} (certeza: ${CERTAINTY_LABELS[value?.certainty] ?? "—"})`;
  }
  if (!Array.isArray(value)) return typeof value === "string" ? value : "—";
  const items = value.map((item) => (typeof item === "string" ? item : `${item?.event_id} · ${item?.description}`));
  if (items.length === 0) return null;
  const list = document.createElement("ul");
  items.forEach((text) => {
    const entry = document.createElement("li");
    entry.textContent = text;
    list.append(entry);
  });
  return list;
}

function sectionRow(title, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = title;
  const definition = document.createElement("dd");
  definition.append(value ?? "Ninguno declarado");
  wrapper.append(term, definition);
  return wrapper;
}

function renderContent(record) {
  const sections = nodes["artifact-sections"];
  sections.replaceChildren();
  nodes["content-restricted"].hidden = record.content_included === true;
  if (record.content_included === true) {
    SECTIONS.forEach(([key, title]) => sections.append(sectionRow(title, sectionValue(key, record.content?.[key]))));
  }
  nodes["artifact-section"].hidden = false;
}

function render(detail, record) {
  nodes["fact-incident"].textContent = state.incidentId;
  nodes["fact-state"].textContent = stateLabel(detail.state);
  nodes["fact-artifact"].textContent = record ? record.postmortem_id : "Sin artefacto persistido";
  nodes["fact-version"].textContent = record ? String(record.version) : "—";
  nodes["fact-review"].textContent = record ? reviewText(record.review) : "—";
  nodes["fact-runs"].textContent = record ? record.run_ids.join(", ") : "—";
  nodes["fact-updated"].textContent = record ? `${record.updated_by} · ${formatTimestamp(record.updated_at)}` : "—";
  nodes["context-section"].hidden = false;
  if (record) {
    renderContent(record);
    return;
  }
  nodes["empty-detail"].textContent =
    EMPTY_DETAILS[detail.state] ??
    `El incidente está en «${stateLabel(detail.state)}». El postmortem se abre cuando el incidente queda resuelto.`;
  nodes["empty-section"].hidden = false;
}

function validRecord(record) {
  return Number.isSafeInteger(record?.version) && typeof record.postmortem_id === "string" && Array.isArray(record.run_ids);
}

async function loadAll() {
  const generation = (state.generation += 1);
  hideAll();
  nodes["loading-state"].hidden = false;
  nodes["postmortem"].dataset.state = "loading";
  try {
    const detail = await client.getIncident(state.incidentId);
    let record = null;
    try {
      record = await client.getPostmortem(state.incidentId);
    } catch (error) {
      // An incident without a persisted artifact is an empty state, not an error.
      if (!(error instanceof ApiClientError) || error.code !== "postmortem_not_found") throw error;
    }
    if (generation !== state.generation) return;
    if (record !== null && !validRecord(record)) {
      showError("503");
      return;
    }
    render(detail, record);
    view.focusIncident(detail, focusRun(detail));
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
    nodes["postmortem"].dataset.state = "ready";
  } catch (error) {
    if (generation !== state.generation) return;
    showError(showKind(error));
  }
}

// La credencial vive en la sesión de la consola: sin sesión activa no queda nada leído.
function dropSession() {
  state.generation += 1;
  hideAll();
  nodes["error-401"].hidden = false;
  nodes["postmortem"].dataset.state = "auth";
}

cacheNodes();
nodes["refresh-button"].addEventListener("click", loadAll);
state.incidentId = view.params.get("incident_id");
state.runId = view.params.get("run_id");
if (!state.incidentId) {
  hideAll();
  nodes["error-missing-id"].hidden = false;
  nodes["postmortem"].dataset.state = "error";
} else {
  view.onSession((session) => (session.phase === "active" ? loadAll() : dropSession()));
}
