import { ApiClientError } from "/public/api/client.js";
import { stateLabel } from "/public/console/incident-vocabulary.js";
import { hrefFor } from "/public/console/routes.js";
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

// Backend refusals of a write, as the operator reads them; the HTTP status and code always show.
const CODE_MESSAGES = Object.freeze({
  run_conflict: "El incidente cambió de estado; actualiza antes de reintentar.",
  not_authorized: "Tu identidad no está autorizada para esta operación.",
  postmortem_version_conflict:
    "El postmortem cambió desde que lo cargaste: actualiza antes de reintentar. Si editabas, tu borrador sigue en el formulario.",
  postmortem_not_open: "El incidente ya no está en postmortem: el artefacto es de solo lectura.",
  invalid_postmortem: "El contenido no cumple el mínimo del postmortem:",
  unknown_event_reference: "Una cita no corresponde a un evento guardado de este incidente.",
});
// The agent drafts through the governed gateway with an existing alias: the caller's grants,
// consumption and audit apply, and a human still edits, saves and approves (#43 CA1, CA4).
const AGENT_ALIAS = "triage-agent";
const FIELDS = ["summary", "impact", "cause", "certainty", "strategy", "timeline", "actions_taken", "verification", "pending", "unknowns"];

const state = { incidentId: null, runId: null, generation: 0, busy: false, startKey: null, baseVersion: 0, notice: null, reviewNotice: null };

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
    "refresh-button", "start-postmortem", "start-status", "editor-section", "editor-form", "editor-basis",
    "save-postmortem", "save-status", ...FIELDS.map((key) => `pm-${key}`), "review-section", "review-title",
    "review-form", "review-comment", "approve-postmortem", "request-changes", "review-status", "close-hint", "decisions-link",
    "agent-draft", "agent-status",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function hideAll() {
  [
    "loading-state", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section", "artifact-section", "empty-section",
    "editor-section", "start-status", "save-status", "review-section", "review-status", "close-hint", "agent-status",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["artifact-sections"].replaceChildren();
  nodes["editor-form"].reset();
  nodes["review-form"].reset();
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

function outcomeMessage(error) {
  if (!(error instanceof ApiClientError)) return "No se pudo confirmar la operación; actualiza antes de reintentar.";
  const known =
    CODE_MESSAGES[error.code] ??
    (error.kind === "authorization" ? CODE_MESSAGES.not_authorized : "El backend no completó la operación; actualiza antes de reintentar.");
  const detail = error.code === "invalid_postmortem" ? ` ${error.message}` : "";
  return `HTTP ${error.status ?? "sin respuesta"}${error.code ? ` · ${error.code}` : ""}. ${known}${detail}`;
}

function showStatus(id, text) {
  nodes[id].textContent = text ?? "";
  nodes[id].hidden = !text;
}

function setBusy(busy) {
  state.busy = busy;
  ["start-postmortem", "save-postmortem", "approve-postmortem", "request-changes", "agent-draft", "refresh-button"].forEach((id) => {
    nodes[id].disabled = busy;
  });
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
  nodes["start-postmortem"].hidden = detail.state !== "resolved";
  nodes["empty-section"].hidden = false;
}

// State changes the incident stored, in order: the only events a draft may cite. Ids outside the
// citation contract (triage writes its declaration as evt-…) are left out instead of failing the save.
const CITABLE = /^evt_[a-z0-9_-]{1,60}$/;
async function storedEvents(detail) {
  const runs = (Array.isArray(detail.runs) ? detail.runs : []).filter((run) => typeof run?.run_id === "string");
  const pages = await Promise.all(
    runs.map((run) => client.getIncidentTimeline(state.incidentId, { runId: run.run_id, limit: 200 })),
  );
  return pages
    .flatMap((page) => (Array.isArray(page.events) ? page.events : []))
    .filter((event) => event.kind === "state_change" && CITABLE.test(event.event_id ?? ""))
    .sort((left, right) => String(left.occurred_at).localeCompare(String(right.occurred_at)));
}

// A first draft from what the incident recorded. An approved mitigation is cited as approved, not
// as executed; the cause stays a hypothesis because the hypothesis text is not part of this read.
function draftFrom(detail, events) {
  const [proposed, applied, verified] = ["mitigating", "verifying", "resolved"].map((target) =>
    events.filter((event) => event.state === target).at(-1),
  );
  const alert = detail.alert;
  return {
    summary: alert ? `${alert.summary} (${alert.service}, ${detail.severity ?? alert.severity}).` : `Incidente ${state.incidentId}.`,
    impact: detail.impact ?? "Impacto no registrado.",
    timeline: events.map((event) => ({ event_id: event.event_id, description: `${stateLabel(event.state)}: ${event.summary}` })),
    cause: proposed
      ? { statement: `La investigación sustentó con evidencia una hipótesis antes de proponer la mitigación (${proposed.event_id}).`, certainty: "hypothesis" }
      : { statement: "Causa no establecida.", certainty: "unknown" },
    strategy: proposed ? `Mitigación propuesta por la investigación (${proposed.event_id}).` : "Sin estrategia registrada.",
    actions_taken: applied
      ? [{ event_id: applied.event_id, description: "Mitigación aprobada por una persona; ejecución humana o simulada, fuera del agente." }]
      : [],
    verification: verified ? `Estabilidad verificada por una persona (${verified.event_id}).` : "Sin verificación registrada.",
    pending: [],
    unknowns: proposed ? [] : ["Causa raíz."],
  };
}

function fillForm(content) {
  const lines = (items) =>
    (Array.isArray(items) ? items : []).map((item) => (typeof item === "string" ? item : `${item.event_id} | ${item.description}`)).join("\n");
  ["summary", "impact", "strategy", "verification"].forEach((key) => {
    nodes[`pm-${key}`].value = content[key] ?? "";
  });
  nodes["pm-cause"].value = content.cause?.statement ?? "";
  nodes["pm-certainty"].value = Object.hasOwn(CERTAINTY_LABELS, content.cause?.certainty ?? "") ? content.cause.certainty : "unknown";
  ["timeline", "actions_taken", "pending", "unknowns"].forEach((key) => {
    nodes[`pm-${key}`].value = lines(content[key]);
  });
}

function formContent() {
  const value = (key) => nodes[`pm-${key}`].value.trim();
  const items = (key) => value(key).split("\n").map((line) => line.trim()).filter(Boolean);
  const cited = (key) =>
    items(key).map((line) => {
      const [eventId, ...rest] = line.split("|");
      return { event_id: eventId.trim(), description: rest.join("|").trim() };
    });
  return {
    summary: value("summary"),
    impact: value("impact"),
    timeline: cited("timeline"),
    cause: { statement: value("cause"), certainty: nodes["pm-certainty"].value },
    strategy: value("strategy"),
    actions_taken: cited("actions_taken"),
    verification: value("verification"),
    pending: items("pending"),
    unknowns: items("unknowns"),
  };
}

// Only the postmortem state takes writes, and never over text this identity cannot read.
function renderEditor(detail, record, events) {
  if (detail.state !== "postmortem" || (record !== null && record.content_included !== true)) return;
  state.baseVersion = record ? record.version : 0;
  fillForm(record ? record.content : draftFrom(detail, events));
  nodes["editor-basis"].textContent = record
    ? `Editas la versión ${record.version}; guardar crea la versión ${record.version + 1} y su revisión queda pendiente.`
    : "Borrador prellenado desde el incidente y sus eventos guardados; guardar crea la versión 1.";
  showStatus("save-status", state.notice);
  state.notice = null;
  nodes["editor-section"].hidden = false;
}

function validRecord(record) {
  return Number.isSafeInteger(record?.version) && typeof record.postmortem_id === "string" && Array.isArray(record.run_ids);
}

// The human review of the version on screen. Approving never closes: close_incident is asked in
// Decisiones on the run that holds the postmortem state, and the backend checks this approval.
function renderReview(detail, record) {
  const postmortemRun = (Array.isArray(detail.runs) ? detail.runs : []).find((run) => run?.current_state === "postmortem");
  if (detail.state !== "postmortem" || record === null || record.content_included !== true) return;
  state.reviewVersion = record.version;
  nodes["review-title"].textContent = `Revisión humana de la versión ${record.version}`;
  nodes["approve-postmortem"].textContent = `Aprobar versión ${record.version}`;
  showStatus("review-status", state.reviewNotice);
  state.reviewNotice = null;
  const approved = record.review?.status === "approved" && typeof postmortemRun?.run_id === "string";
  if (approved) nodes["decisions-link"].href = hrefFor("decisions", { incident_id: state.incidentId, run_id: postmortemRun.run_id });
  nodes["close-hint"].hidden = !approved;
  nodes["review-section"].hidden = false;
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
    const events = detail.state === "postmortem" && record === null ? await storedEvents(detail) : [];
    if (generation !== state.generation) return;
    state.workflowVersion = detail.workflow_version;
    state.detail = detail;
    state.postmortemRun = (detail.runs ?? []).find((run) => run?.current_state === "postmortem")?.run_id;
    state.startKey = `postmortem-start-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
    render(detail, record);
    renderEditor(detail, record, events);
    renderReview(detail, record);
    view.focusIncident(detail, focusRun(detail));
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
    nodes["postmortem"].dataset.state = "ready";
  } catch (error) {
    if (generation !== state.generation) return;
    showError(showKind(error));
  }
}

// start_postmortem through the objective route; one key per read, so a retry never opens twice.
async function startPostmortem() {
  if (state.busy) return;
  const generation = state.generation;
  setBusy(true);
  showStatus("start-status", "Abriendo el postmortem…");
  try {
    const body = { workflow_version: state.workflowVersion, objective: "postmortem" };
    await client.startRun(state.incidentId, body, state.startKey);
    if (generation !== state.generation) return;
    setBusy(false);
    await loadAll();
  } catch (error) {
    if (generation === state.generation) showStatus("start-status", outcomeMessage(error));
  } finally {
    setBusy(false);
  }
}

async function savePostmortem(event) {
  event.preventDefault();
  if (state.busy) return;
  const generation = state.generation;
  setBusy(true);
  showStatus("save-status", "Guardando…");
  try {
    const body = { expected_version: state.baseVersion, content: formContent() };
    const saved = await client.putPostmortem(state.incidentId, body);
    if (generation !== state.generation) return;
    state.notice = `Versión ${saved.version} guardada por ${saved.updated_by}. Su revisión queda pendiente.`;
    setBusy(false);
    await loadAll();
  } catch (error) {
    if (generation === state.generation) showStatus("save-status", outcomeMessage(error));
  } finally {
    setBusy(false);
  }
}

async function reviewPostmortem(outcome) {
  if (state.busy) return;
  const generation = state.generation;
  setBusy(true);
  showStatus("review-status", "Registrando la revisión…");
  try {
    const comment = nodes["review-comment"].value.trim();
    const body = { version: state.reviewVersion, outcome, ...(comment ? { comment } : {}) };
    const { review } = await client.reviewPostmortem(state.incidentId, body);
    if (generation !== state.generation) return;
    state.reviewNotice = `${REVIEW_LABELS[review.status] ?? review.status}: revisión de la versión ${review.reviewed_version} registrada por ${review.reviewer_id}.`;
    setBusy(false);
    await loadAll();
  } catch (error) {
    if (generation === state.generation) showStatus("review-status", outcomeMessage(error));
  } finally {
    setBusy(false);
  }
}

// What the agent may use: the incident read, every stored event and, when this identity can read
// them, the agent turns of each run. Only stored, contract-valid event ids may be cited.
async function agentPrompt(detail) {
  const runs = (detail.runs ?? []).map((run) => run?.run_id).filter((id) => typeof id === "string");
  const read = (runId) => client.getIncidentTimeline(state.incidentId, { runId, limit: 200 });
  const events = (await Promise.all(runs.map(read))).flatMap((page) => page.events ?? []);
  const contexts = await Promise.all(runs.map((runId) => client.getRunContext(state.incidentId, runId).catch(() => null)));
  const outputs = contexts.flatMap((context) => context?.turns ?? []).map((turn) => turn.model_output).filter(Boolean);
  const citable = events.filter((event) => CITABLE.test(event.event_id ?? ""));
  const row = (event) => [event.event_id, event.kind, event.state, event.actor?.type, event.occurred_at, event.summary].join(" | ");
  const facts = { incident_id: detail.incident_id, state: detail.state, severity: detail.severity, impact: detail.impact, alert: detail.alert };
  const input = [
    "Draft the minimum postmortem of this incident for a human reviewer, in Spanish. Use only the facts below; never invent events, actions or causes.",
    "Answer with only a JSON object with exactly the keys summary, impact, timeline, cause, strategy, actions_taken, verification, pending, unknowns.",
    'summary, impact, strategy, verification: short nonblank text. cause: {"statement": text, "certainty": "confirmed"|"probable"|"hypothesis"|"unknown"}.',
    'timeline (at least one): list of {"event_id": a citable id, "description": text}, the key moments in order.',
    "actions_taken: same shape, only actions taken on the service (such as an approved mitigation), each with the citable event that confirms it. Do not repeat workflow steps; an approval is not an execution.",
    "pending and unknowns: lists of text. Declare what is not known instead of guessing.",
    `Incident: ${JSON.stringify(facts)}`,
    `Citable events (event_id | kind | state | actor | occurred_at | summary):\n${citable.map(row).join("\n")}`,
    `Agent turns of this incident (truncated):\n${outputs.map((text) => String(text).slice(0, 2000)).join("\n---\n") || "none"}`,
  ].join("\n\n");
  return { input: input.slice(0, 60000), citable: new Set(citable.map((event) => event.event_id)) };
}

function parseDraft(response, citable) {
  const text = (response?.output ?? []).flatMap((item) => item?.content ?? []).map((part) => part?.text ?? "").join("");
  let draft;
  try {
    draft = JSON.parse(text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1));
  } catch {
    return null;
  }
  if (!draft || typeof draft !== "object" || !SECTIONS.every(([key]) => key in draft)) return null;
  let dropped = 0;
  const keep = (items) =>
    (Array.isArray(items) ? items : []).filter((item) => citable.has(item?.event_id) || ((dropped += 1), false));
  return { draft: { ...draft, timeline: keep(draft.timeline), actions_taken: keep(draft.actions_taken) }, dropped };
}

async function agentDraft() {
  if (state.busy) return;
  const generation = state.generation;
  setBusy(true);
  showStatus("agent-status", `Pidiendo un borrador al agente (alias ${AGENT_ALIAS}) por el gateway gobernado; puede tardar hasta 3 minutos…`);
  try {
    const { input, citable } = await agentPrompt(state.detail);
    const body = { model: AGENT_ALIAS, input, incident_id: state.incidentId, ...(state.postmortemRun ? { run_id: state.postmortemRun } : {}) };
    const response = await client.createResponse(body);
    if (generation !== state.generation) return;
    const parsed = parseDraft(response, citable);
    if (!parsed) {
      showStatus("agent-status", "La respuesta del agente no es un borrador válido; el formulario no cambió.");
      return;
    }
    fillForm(parsed.draft);
    const cost = response.metadata?.consumption?.billed_usd;
    const dropped = parsed.dropped ? ` ${parsed.dropped} ${parsed.dropped === 1 ? "cita descartada" : "citas descartadas"}: no son eventos guardados.` : "";
    showStatus(
      "agent-status",
      `Borrador del agente (${AGENT_ALIAS} → ${response.model}, request ${response.request_id}${cost ? `, USD ${cost}` : ""}). ` +
        `No está guardado: revísalo, corrígelo y guárdalo; la aprobación sigue siendo humana.${dropped}`,
    );
  } catch (error) {
    if (generation !== state.generation) return;
    const grant = error?.kind === "authorization" ? ` Requiere el grant invoke sobre llm_model/${AGENT_ALIAS}.` : "";
    showStatus("agent-status", `${outcomeMessage(error)}${grant} El formulario no cambió.`);
  } finally {
    setBusy(false);
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
nodes["start-postmortem"].addEventListener("click", startPostmortem);
nodes["editor-form"].addEventListener("submit", savePostmortem);
nodes["approve-postmortem"].addEventListener("click", () => reviewPostmortem("approved"));
nodes["request-changes"].addEventListener("click", () => reviewPostmortem("changes_requested"));
nodes["agent-draft"].addEventListener("click", agentDraft);
state.incidentId = view.params.get("incident_id");
state.runId = view.params.get("run_id");
if (!state.incidentId) {
  hideAll();
  nodes["error-missing-id"].hidden = false;
  nodes["postmortem"].dataset.state = "error";
} else {
  view.onSession((session) => (session.phase === "active" ? loadAll() : dropSession()));
}
