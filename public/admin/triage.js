import { ApiClientError } from "/public/api/client.js";
import { hrefFor } from "/public/console/routes.js";
import { mountedView } from "/public/console/view.js";

const view = mountedView();
const page = document.getElementById("triage-page");
const commandForm = document.getElementById("command-form");
const alertInput = document.getElementById("alert-id");
const versionInput = document.getElementById("expected-version");
const operationInput = document.getElementById("command-operation");
const reasonInput = document.getElementById("command-reason");
const targetInput = document.getElementById("command-target");
const targetListStatus = document.getElementById("target-list-status");
const severityInput = document.getElementById("command-severity");
const impactInput = document.getElementById("command-impact");
const alertContextFields = document.getElementById("alert-context-fields");
const alertContextServiceInput = document.getElementById("alert-context-service");
const alertContextSummaryInput = document.getElementById("alert-context-summary");
const alertContextObservedAtInput = document.getElementById("alert-context-observed-at");
const alertContextSourceInput = document.getElementById("alert-context-source");
const alertContextSeverityInput = document.getElementById("alert-context-severity");
const alertContextConfirmedInput = document.getElementById("alert-context-confirmed");
const submitButton = document.getElementById("submit-button");
const actionsStatus = document.getElementById("actions-status");
const liveRegion = document.getElementById("live-region");
const errorBox = document.getElementById("page-error");
const errorTitle = document.getElementById("page-error-title");
const errorDetail = document.getElementById("page-error-detail");
const stateLine = document.getElementById("triage-state");
const resultSummary = document.getElementById("result-summary");
const resultOperation = document.getElementById("result-operation");
const resultStatus = document.getElementById("result-status");
const resultReason = document.getElementById("result-reason");
const resultIncident = document.getElementById("result-incident");
const resultVersion = document.getElementById("result-version");
const resultActor = document.getElementById("result-actor");
const resultDecided = document.getElementById("result-decided");
const resultOrigin = document.getElementById("result-origin");
const resultResponsibleSystem = document.getElementById("result-responsible-system");

const controlApi = view.client;
let sessionGeneration = 0;
let commandInFlight = false;
let contextGeneration = 0;
let sessionActive = false;
let contextAlertId = "";
let allowedActions = null;
let lastObservedAlertId = "";
let contextTimer = null;
let eligibleGeneration = 0;
let eligibleAlertId = "";
let eligibleSessionGeneration = 0;
let eligibleIncidents = null;

const ELIGIBLE_INCIDENT_STATES = new Set(["active", "investigating", "mitigating", "verifying"]);
const INCIDENT_ID_PATTERN = /^[a-z][a-z0-9_-]{2,63}$/;

const text = (value) => (typeof value === "string" ? value : "");
const DECISION_ORIGIN_LABELS = Object.freeze({
  manual: "Manual",
  external_automatic: "Automática externa",
  unknown: "Desconocido (histórico)",
});
const announce = (message) => {
  liveRegion.textContent = message;
};

function newCommandKey() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `triage-${[...bytes].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}

function describeError(error, scope = "command") {
  if (error?.kind === "network")
    return ["API no disponible", "No se pudo contactar la API de triage. Revisa el stack y reintenta."];
  if (error?.kind === "authentication")
    return ["Autenticación requerida", "Conecta la consola con una API key válida. No se confirmó nada más."];
  if (error?.kind === "authorization")
    return scope === "read"
      ? ["Sin acceso", "Esta identidad no puede leer el estado de triage."]
      : ["Sin acceso", "El comando no se puede confirmar para esta identidad."];
  if (error?.kind === "not_found")
    return ["No encontrado", "Alerta o incidente destino desconocido. No se cambió nada."];
  if (error?.kind === "validation")
    return ["Solicitud inválida", text(error?.message) || "Revisa los campos del comando e inténtalo de nuevo."];
  if (error?.kind === "conflict")
    return [
      "Conflicto",
      text(error?.message) || "La versión está desactualizada o la clave del comando ya se usó. Actualiza el estado.",
    ];
  if (error?.kind === "api" && error?.status === 422)
    return ["Solicitud inválida", error?.message ?? "La API rechazó el cuerpo del comando."];
  if (error?.kind === "api" && error?.code === "storage_unavailable")
    return ["Servicio no disponible", error?.message ?? "La solicitud no se completó. Reintenta."];
  if (error?.kind === "api")
    return ["La solicitud falló", error?.message ?? "Error inesperado. No se cambió nada."];
  return ["La solicitud falló", error?.message ?? "Error inesperado."];
}

function showError(error, scope = "command") {
  const [title, detail] = describeError(error, scope);
  errorTitle.textContent = title;
  errorDetail.textContent = detail;
  errorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function hideError() {
  errorBox.hidden = true;
  errorDetail.textContent = "";
}

function invalidateEligibleIncidents(message = "Elige triage_link para cargar los incidentes elegibles del backend.") {
  eligibleGeneration += 1;
  eligibleAlertId = "";
  eligibleSessionGeneration = 0;
  eligibleIncidents = null;
  targetInput.replaceChildren(new Option("Elige un incidente elegible…", ""));
  targetInput.value = "";
  targetInput.disabled = true;
  targetListStatus.textContent = message;
}

function validEligibleResponse(response) {
  if (!response || typeof response !== "object" || !Array.isArray(response.items) || response.items.length > 100)
    return false;
  const seen = new Set();
  return response.items.every((item) => {
    if (!item || typeof item !== "object" || !INCIDENT_ID_PATTERN.test(item.incident_id) ||
      !ELIGIBLE_INCIDENT_STATES.has(item.state) || seen.has(item.incident_id)) return false;
    seen.add(item.incident_id);
    return true;
  });
}

function renderEligibleIncidents(items, selectedTarget = "") {
  targetInput.replaceChildren(new Option("Elige un incidente elegible…", ""));
  for (const item of items) {
    targetInput.add(new Option(`${item.incident_id} · ${item.state}`, item.incident_id));
  }
  targetInput.value = items.some((item) => item.incident_id === selectedTarget) ? selectedTarget : "";
  targetListStatus.textContent = items.length === 0
    ? "El backend no devolvió incidentes elegibles."
    : `Se muestran hasta 100 incidentes elegibles; la lista puede estar incompleta (${items.length} devueltos).`;
}

function eligibleListIsCurrent(alertId = alertInput.value.trim()) {
  return sessionActive && eligibleAlertId === alertId &&
    eligibleSessionGeneration === sessionGeneration && Array.isArray(eligibleIncidents) &&
    contextAlertId === alertId && allowedActions?.includes("triage_link");
}

async function loadEligibleIncidents({ force = false, preserveSelection = false, selectedTarget = "" } = {}) {
  const alertId = alertInput.value.trim();
  if (!sessionActive || contextAlertId !== alertId || !allowedActions?.includes("triage_link") ||
    operationInput.value !== "triage_link") {
    invalidateEligibleIncidents();
    updateActionControls();
    return { ok: false };
  }
  if (!force && eligibleListIsCurrent(alertId)) return { ok: true, items: eligibleIncidents };

  const requestGeneration = ++eligibleGeneration;
  const generation = sessionGeneration;
  const selectedBeforeRead = preserveSelection ? selectedTarget || targetInput.value : "";
  eligibleAlertId = "";
  eligibleSessionGeneration = 0;
  eligibleIncidents = null;
  targetInput.replaceChildren(new Option("Elige un incidente elegible…", ""));
  targetInput.value = "";
  targetInput.disabled = true;
  targetListStatus.textContent = "Cargando los incidentes elegibles del backend…";
  updateActionControls();
  try {
    const response = await controlApi.getEligibleIncidents(alertId);
    if (requestGeneration !== eligibleGeneration || generation !== sessionGeneration ||
      !sessionActive || alertInput.value.trim() !== alertId || contextAlertId !== alertId ||
      !allowedActions?.includes("triage_link") || operationInput.value !== "triage_link")
      return { ok: false, stale: true };
    if (!validEligibleResponse(response)) throw new ApiClientError("invalid_response", "La API devolvió una lista de incidentes elegibles inválida.");
    eligibleAlertId = alertId;
    eligibleSessionGeneration = generation;
    eligibleIncidents = response.items;
    renderEligibleIncidents(response.items, preserveSelection ? selectedBeforeRead : "");
    targetInput.disabled = response.items.length === 0;
    updateActionControls();
    return { ok: true, items: response.items };
  } catch (error) {
    if (requestGeneration !== eligibleGeneration || generation !== sessionGeneration ||
      !sessionActive || alertInput.value.trim() !== alertId || contextAlertId !== alertId ||
      operationInput.value !== "triage_link") return { ok: false, stale: true };
    eligibleAlertId = "";
    eligibleSessionGeneration = 0;
    eligibleIncidents = null;
    targetInput.replaceChildren(new Option("Elige un incidente elegible…", ""));
    targetInput.value = "";
    targetInput.disabled = true;
    targetListStatus.textContent = "No se pudieron cargar los incidentes elegibles. No hay destino para vincular.";
    updateActionControls();
    showError(error, "read");
    return { ok: false, error };
  }
}

function clearResultDisplay(summary) {
  resultOperation.textContent = "—";
  resultStatus.textContent = "—";
  resultReason.textContent = "—";
  resultIncident.textContent = "—";
  resultVersion.textContent = "—";
  resultActor.textContent = "—";
  resultDecided.textContent = "—";
  resultOrigin.textContent = "—";
  resultResponsibleSystem.textContent = "—";
  resultSummary.textContent = summary;
}

function updateActionControls() {
  const hasProjection = contextAlertId === alertInput.value.trim() && allowedActions !== null;
  for (const option of operationInput.options) {
    option.disabled = !hasProjection || !allowedActions.includes(option.value);
  }
  operationInput.disabled = commandInFlight || !hasProjection || allowedActions.length === 0;
  alertInput.disabled = commandInFlight;
  const validTarget = eligibleListIsCurrent() &&
    eligibleIncidents.some((item) => item.incident_id === targetInput.value);
  targetInput.disabled = commandInFlight || operationInput.value !== "triage_link" ||
    !eligibleListIsCurrent() || eligibleIncidents.length === 0;
  submitButton.disabled =
    commandInFlight || !hasProjection || !allowedActions.includes(operationInput.value) ||
    (operationInput.value === "triage_link" && !validTarget);
}

function clearActionProjection() {
  invalidateEligibleIncidents();
  contextAlertId = "";
  allowedActions = null;
  actionsStatus.textContent = sessionActive
    ? "Cargando las operaciones que permite el backend…"
    : "Conecta la consola y elige una alerta para cargar las acciones del backend.";
  updateActionControls();
}

function isValidContext(item, alertId) {
  const actions = ["open_triage", "triage_dismiss", "triage_link", "triage_declare"];
  if (
    item === null || typeof item !== "object" || item.alert_id !== alertId ||
    !Array.isArray(item.allowed_actions) ||
    item.allowed_actions.some((action) => !actions.includes(action)) ||
    new Set(item.allowed_actions).size !== item.allowed_actions.length
  ) return false;
  if (item.triage_state === null) return true;
  const state = item.triage_state;
  return state !== null && typeof state === "object" && state.alert_id === alertId &&
    ["open", "dismissed", "linked", "declared"].includes(state.status) &&
    Number.isInteger(state.expected_version) && state.expected_version > 0;
}

function renderContextState(alertId, state) {
  if (state === null) {
    clearResultDisplay("Esta alerta no tiene una decisión registrada.");
    stateLine.textContent = `La alerta ${alertId} aún no tiene una decisión registrada.`;
    versionInput.value = "1";
  } else {
    setResult(state.status, state, "recovered");
  }
}

function setResult(operation, item, source = "live") {
  resultOperation.textContent = operation;
  resultStatus.textContent = text(item.status) || "—";
  resultReason.textContent = text(item.reason) || "—";
  const incident = text(item.incident_id);
  resultIncident.replaceChildren();
  if (incident === "") {
    resultIncident.textContent = "—";
  } else {
    const link = document.createElement("a");
    link.href = hrefFor("war-room", { incident_id: incident });
    link.textContent = incident;
    resultIncident.appendChild(link);
  }
  resultVersion.textContent = item.expected_version === undefined ? "—" : String(item.expected_version);
  resultActor.textContent = text(item.actor) || "—";
  resultDecided.textContent = text(item.decided_at) || "—";
  const origin = text(item.decision_origin);
  resultOrigin.textContent = DECISION_ORIGIN_LABELS[origin] ?? "—";
  const responsibleSystem = text(item.responsible_system);
  resultResponsibleSystem.textContent =
    origin === "external_automatic" && responsibleSystem.trim() !== ""
      ? responsibleSystem
      : "—";
  versionInput.value = item.expected_version === undefined ? versionInput.value : String(item.expected_version);
  if (source === "recovered") {
    resultSummary.textContent =
      `Recuperado del backend: ${text(item.status)}` + (incident === "" ? "." : `, incidente ${incident}.`);
    stateLine.textContent =
      `La alerta ${alertInput.value.trim()} está ${text(item.status)} (versión ${String(item.expected_version)}), según la API.`;
  } else {
    resultSummary.textContent =
      `${operation} aplicada: ${text(item.status)}` + (incident === "" ? "." : `, incidente ${incident}.`);
    stateLine.textContent =
      `La alerta ${alertInput.value.trim()} está ${text(item.status)} (versión ${String(item.expected_version)}).`;
  }
  announce(resultSummary.textContent);
}

function clearResult() {
  clearResultDisplay("Aún no se envió ningún comando.");
  stateLine.textContent = "Conecta la consola para empezar.";
  versionInput.value = "1";
  alertInput.value = "";
  reasonInput.value = "";
  targetInput.value = "";
  severityInput.value = "";
  impactInput.value = "";
  clearDeclarationContext();
  lastObservedAlertId = "";
}

const OPERATION_FIELDS = Object.freeze({
  open_triage: Object.freeze([]),
  triage_dismiss: Object.freeze(["reason"]),
  triage_link: Object.freeze(["reason", "target_incident_id"]),
  triage_declare: Object.freeze(["reason", "severity", "impact"]),
});

const ALERT_CONTEXT_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function clearDeclarationContext() {
  alertContextServiceInput.value = "";
  alertContextSummaryInput.value = "";
  alertContextObservedAtInput.value = "";
  alertContextSourceInput.value = "";
  alertContextSeverityInput.value = "";
  alertContextConfirmedInput.checked = false;
}

function updateDeclarationContextControls() {
  const required = operationInput.value === "triage_declare";
  alertContextFields.hidden = !required;
  for (const input of [
    alertContextServiceInput,
    alertContextSummaryInput,
    alertContextObservedAtInput,
    alertContextSourceInput,
    alertContextSeverityInput,
    alertContextConfirmedInput,
  ]) {
    input.setAttribute("aria-required", String(required));
  }
}

function buildDeclarationAlertContext() {
  const context = {
    service: alertContextServiceInput.value,
    summary: alertContextSummaryInput.value,
    observed_at: alertContextObservedAtInput.value,
    source: alertContextSourceInput.value,
    severity: alertContextSeverityInput.value,
  };
  if (
    context.service.trim() === "" || context.service.length > 200 ||
    context.summary.trim() === "" || context.summary.length > 2000 ||
    !ALERT_CONTEXT_TIMESTAMP.test(context.observed_at) ||
    context.source.trim() === "" || context.source.length > 200 ||
    !["sev1", "sev2", "sev3", "sev4"].includes(context.severity) ||
    !alertContextConfirmedInput.checked
  ) return { ok: false };
  return { ok: true, context };
}

function buildBody(operation) {
  const versionText = versionInput.value.trim();
  const version = versionText === "" ? Number.NaN : Number(versionText);
  if (!Number.isInteger(version) || version < 1)
    return { ok: false, message: "Escribe la versión esperada del estado actual." };
  const fields = OPERATION_FIELDS[operation];
  if (fields === undefined)
    return { ok: false, message: "Elige una operación admitida." };
  const body = { operation, expected_version: version };
  const reason = reasonInput.value.trim();
  if (reason !== "" && fields.includes("reason")) body.reason = reason;
  const target = targetInput.value.trim();
  if (fields.includes("target_incident_id")) {
    if (!eligibleListIsCurrent() || !eligibleIncidents.some((item) => item.incident_id === target))
      return { ok: false, message: "Elige un destino de la última lista de incidentes elegibles del backend." };
    body.target_incident_id = target;
  }
  const severity = severityInput.value;
  if (severity !== "" && fields.includes("severity")) body.severity = severity;
  const impact = impactInput.value;
  impactInput.setAttribute("aria-required", String(fields.includes("impact")));
  if (fields.includes("impact")) {
    if (impact.trim() === "")
      return { ok: false, message: "El impacto es obligatorio para declarar un incidente." };
    if (impact.length > 2000)
      return { ok: false, message: "El impacto admite como máximo 2000 caracteres." };
    body.impact = impact;
  }
  if (operation === "triage_declare") {
    const alertContext = buildDeclarationAlertContext();
    if (!alertContext.ok) {
      return {
        ok: false,
        message: "Escribe y confirma el servicio, el resumen, la hora observada, la fuente y la severidad reales de la alerta.",
      };
    }
    body.alert_context = alertContext.context;
  }
  return { ok: true, body };
}

async function readTriageContext(
  alertId,
  generation,
  { preserveResult = false, confirmedCommand = false, showReadError = true, preserveTarget = false } = {},
) {
  const requestGeneration = ++contextGeneration;
  const targetToPreserve = preserveTarget ? targetInput.value : "";
  invalidateEligibleIncidents("Cargando los permisos actuales de la alerta y los destinos elegibles…");
  contextAlertId = "";
  allowedActions = null;
  actionsStatus.textContent = "Cargando las operaciones que permite el backend…";
  updateActionControls();
  page.dataset.state = "loading";
  try {
    const item = await controlApi.getTriageContext(alertId);
    if (
      generation !== sessionGeneration || requestGeneration !== contextGeneration ||
      alertInput.value.trim() !== alertId || !sessionActive
    ) return { ok: false, stale: true };
    if (!isValidContext(item, alertId)) {
      throw new ApiClientError("invalid_response", "La API devolvió un contexto de triage inválido.");
    }
    if (confirmedCommand && item.triage_state === null) {
      contextAlertId = "";
      allowedActions = null;
      actionsStatus.textContent = "El resultado del comando está confirmado, pero la API no devolvió estado de triage; las siguientes operaciones quedan deshabilitadas.";
      updateActionControls();
      page.dataset.state = "error";
      const error = new ApiClientError(
        "invalid_response",
        "El comando se confirmó, pero el contexto del backend no tiene estado de triage. Las siguientes operaciones quedan deshabilitadas.",
      );
      stateLine.textContent = "El resultado del comando está confirmado; las operaciones actuales no están disponibles.";
      if (showReadError) showError(error, "read");
      return { ok: false, error };
    }
    contextAlertId = alertId;
    allowedActions = [...item.allowed_actions];
    actionsStatus.textContent = allowedActions.length === 0
      ? "El backend no permite ahora ninguna operación de triage para esta alerta."
      : "Las operaciones habilitadas son las que el backend permite a esta identidad para esta alerta.";
    updateActionControls();
    renderContextState(alertId, item.triage_state);
    page.dataset.state = "ready";
    hideError();
    if (operationInput.value === "triage_link" && allowedActions.includes("triage_link")) {
      void loadEligibleIncidents({ preserveSelection: preserveTarget, selectedTarget: targetToPreserve });
    } else {
      targetListStatus.textContent = "Los destinos elegibles solo aplican a un triage_link que el backend permite.";
    }
    return { ok: true, item };
  } catch (error) {
    if (
      generation !== sessionGeneration || requestGeneration !== contextGeneration ||
      alertInput.value.trim() !== alertId || !sessionActive
    ) return { ok: false, stale: true };
    contextAlertId = "";
    allowedActions = null;
    actionsStatus.textContent = preserveResult
      ? "El resultado del comando está confirmado; no se pudieron actualizar las siguientes operaciones permitidas."
      : "No hay operaciones disponibles hasta poder leer el contexto del backend.";
    updateActionControls();
    if (!preserveResult) clearResultDisplay("No se pudo verificar el estado actual; no se confirmó ningún comando.");
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    if (preserveResult) {
      stateLine.textContent = "El resultado del comando está confirmado; las operaciones actuales no están disponibles.";
    } else {
      stateLine.textContent = `El estado actual de la alerta ${alertId} no está disponible.`;
    }
    if (showReadError) showError(error, "read");
    return { ok: false, error };
  }
}

async function refreshAfterConflict(alertId, generation) {
  const refreshed = await readTriageContext(alertId, generation, { showReadError: false, preserveTarget: true });
  if (refreshed.stale) return;
  if (refreshed.ok) {
    page.dataset.state = "error";
    showError({
      kind: "conflict",
      message: "La versión del comando está desactualizada. Se muestra el estado actual de la API; revisa el contexto del comando y envíalo de nuevo.",
    });
  } else {
    const readError = refreshed.error;
    const [readTitle, readDetail] = describeError(readError, "read");
    clearResultDisplay("No se pudo verificar el estado actual; no se confirmó ningún comando.");
    showError({
      kind: "conflict",
      message: `La versión del comando está desactualizada. No se pudo actualizar el estado actual (${readTitle}: ${readDetail}). No se reintentó ni confirmó ningún comando.`,
    });
  }
}

async function sendCommand() {
  if (commandInFlight) return;
  const alertId = alertInput.value.trim();
  if (alertId === "") {
    showError({ kind: "validation", message: "Escribe el identificador de la alerta." });
    return;
  }
  const operation = operationInput.value;
  if (contextAlertId !== alertId || !allowedActions?.includes(operation)) {
    showError({ kind: "validation", message: "Elige una operación que el backend permita ahora." });
    updateActionControls();
    return;
  }
  const checked = buildBody(operation);
  if (!checked.ok) {
    showError({ kind: "validation", message: checked.message });
    return;
  }
  const generation = sessionGeneration;
  const idempotencyKey = newCommandKey();
  commandInFlight = true;
  updateActionControls();
  hideError();
  page.dataset.state = "loading";
  announce(`Enviando ${operation}.`);
  try {
    const item = await controlApi.postTriageCommand(alertId, checked.body, idempotencyKey);
    if (generation !== sessionGeneration) return;
    page.dataset.state = "ready";
    setResult(operation, item ?? {});
    view.replaceParams({ alert_id: alertId });
    await readTriageContext(alertId, generation, { preserveResult: true, confirmedCommand: true });
  } catch (error) {
    if (generation !== sessionGeneration) return;
    if (error?.kind === "conflict" && error?.code === "stale_version") {
      await refreshAfterConflict(alertId, generation);
    } else if (error?.kind === "conflict" && error?.code === "destination_ineligible") {
      invalidateEligibleIncidents("El destino ya no es elegible. Se actualiza la lista; elige un destino de nuevo.");
      await loadEligibleIncidents({ force: true });
      if (generation !== sessionGeneration || !sessionActive || alertInput.value.trim() !== alertId) return;
      page.dataset.state = "error";
      showError(error);
    } else {
      if (error?.kind === "authorization") {
        contextGeneration += 1;
        clearActionProjection();
        actionsStatus.textContent = "El comando fue denegado; vuelve a cargar los permisos del backend antes de reintentar.";
      }
      page.dataset.state = error?.kind === "network" ? "offline" : "error";
      showError(error);
    }
  } finally {
    if (generation === sessionGeneration) {
      commandInFlight = false;
      updateActionControls();
    }
  }
}

commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCommand();
});

operationInput.addEventListener("change", () => {
  updateDeclarationContextControls();
  impactInput.setAttribute(
    "aria-required",
    String(OPERATION_FIELDS[operationInput.value]?.includes("impact") ?? false),
  );
  hideError();
  if (operationInput.value === "triage_link") {
    void loadEligibleIncidents();
  } else {
    invalidateEligibleIncidents();
  }
  updateActionControls();
});

targetInput.addEventListener("change", () => {
  hideError();
  updateActionControls();
});

alertInput.addEventListener("input", () => {
  const alertId = alertInput.value.trim();
  if (alertId === lastObservedAlertId) return;
  lastObservedAlertId = alertId;
  clearDeclarationContext();
  contextGeneration += 1;
  clearActionProjection();
  clearResultDisplay("Cargando el contexto actual de la alerta desde el backend.");
  versionInput.value = "1";
  if (!sessionActive) return;
  hideError();
  if (!/^[a-z][a-z0-9_-]{2,63}$/.test(alertId)) {
    actionsStatus.textContent = "Escribe un identificador de alerta válido para cargar las operaciones que permite el backend.";
    page.dataset.state = "idle";
    return;
  }
  clearTimeout(contextTimer);
  contextTimer = setTimeout(() => readContextForCurrentAlert(), 120);
});

alertInput.addEventListener("change", () => {
  clearTimeout(contextTimer);
  readContextForCurrentAlert();
});

function readContextForCurrentAlert() {
  if (!sessionActive) return;
  const alertId = alertInput.value.trim();
  if (contextAlertId === alertId && allowedActions !== null) return;
  if (!/^[a-z][a-z0-9_-]{2,63}$/.test(alertId)) return;
  readTriageContext(alertId, sessionGeneration);
}

async function recoverDecision(alertId) {
  if (!/^[a-z][a-z0-9_-]{2,63}$/.test(alertId)) {
    showError({ kind: "validation", message: "Escribe el identificador de la alerta." }, "read");
    return;
  }
  hideError();
  announce("Cargando el contexto de triage de la alerta y las operaciones que autoriza el backend.");
  return readTriageContext(alertId, sessionGeneration);
}

// The console session replaces this view's own key. Its first activation recovers the alert in
// the address, or the one left in the field; a credential change or a logout resets the form.
let deepLinkPending = true;

function startSession() {
  sessionGeneration += 1;
  sessionActive = true;
  contextGeneration += 1;
  commandInFlight = false;
  alertInput.disabled = false;
  clearActionProjection();
  const deepLinkAlertId = deepLinkPending ? alertInput.value.trim() : "";
  deepLinkPending = false;
  clearResult();
  if (/^[a-z][a-z0-9_-]{2,63}$/.test(deepLinkAlertId)) alertInput.value = deepLinkAlertId;
  lastObservedAlertId = alertInput.value.trim();
  hideError();
  page.dataset.state = "idle";
  stateLine.textContent = "Sesión activa. Escribe una alerta y envía un comando.";
  const alertId = alertInput.value.trim();
  if (alertId !== "") recoverDecision(alertId);
  else actionsStatus.textContent = "Escribe el ID de una alerta para cargar las operaciones que permite el backend.";
}

function endSession() {
  sessionGeneration += 1;
  sessionActive = false;
  contextGeneration += 1;
  commandInFlight = false;
  alertInput.disabled = false;
  clearActionProjection();
  hideError();
  page.dataset.state = "idle";
  clearResult();
  deepLinkPending = false;
  view.replaceParams({ alert_id: null });
}

const initialAlertId = view.params.get("alert_id") ?? "";
if (/^[a-z][a-z0-9_-]{2,63}$/.test(initialAlertId)) alertInput.value = initialAlertId;
lastObservedAlertId = alertInput.value.trim();

page.dataset.state = "idle";
updateDeclarationContextControls();
clearActionProjection();
view.signal.addEventListener("abort", () => clearTimeout(contextTimer), { once: true });
view.onSession((session) => {
  if (session.phase === "active") startSession();
  else if (sessionActive) endSession();
});
