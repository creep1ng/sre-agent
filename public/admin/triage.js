import {
  ApiClientError,
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const page = document.getElementById("triage-page");
const sessionForm = document.getElementById("session-form");
const apiKeyInput = document.getElementById("api-key");
const commandForm = document.getElementById("command-form");
const alertInput = document.getElementById("alert-id");
const versionInput = document.getElementById("expected-version");
const operationInput = document.getElementById("command-operation");
const reasonInput = document.getElementById("command-reason");
const targetInput = document.getElementById("command-target");
const severityInput = document.getElementById("command-severity");
const impactInput = document.getElementById("command-impact");
const submitButton = document.getElementById("submit-button");
const actionsStatus = document.getElementById("actions-status");
const disconnectButton = document.getElementById("disconnect-button");
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

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let sessionGeneration = 0;
let commandInFlight = false;
let contextGeneration = 0;
let sessionActive = false;
let contextAlertId = "";
let allowedActions = null;
let lastObservedAlertId = "";
let contextTimer = null;

const text = (value) => (typeof value === "string" ? value : "");
const DECISION_ORIGIN_LABELS = Object.freeze({
  manual: "Manual",
  external_automatic: "External automatic",
  unknown: "Unknown (legacy)",
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
    return ["API unavailable", "The triage API could not be reached. Check the stack and retry."];
  if (error?.kind === "authentication")
    return ["Authentication required", "Provide a valid API key. Nothing else is confirmed."];
  if (error?.kind === "authorization")
    return scope === "read"
      ? ["Access unavailable", "This identity cannot read triage state."]
      : ["Access unavailable", "The command cannot be confirmed for this identity."];
  if (error?.kind === "not_found")
    return ["Not found", "Unknown alert or target incident. Nothing was changed."];
  if (error?.kind === "validation")
    return ["Invalid request", text(error?.message) || "Review the command fields and try again."];
  if (error?.kind === "conflict")
    return [
      "Conflict",
      text(error?.message) || "The version is stale or the command key was reused. Refresh state.",
    ];
  if (error?.kind === "api" && error?.status === 422)
    return ["Invalid request", error?.message ?? "The command payload was rejected."];
  if (error?.kind === "api" && error?.code === "storage_unavailable")
    return ["Service unavailable", error?.message ?? "The request was not completed. Retry."];
  if (error?.kind === "api")
    return ["Request failed", error?.message ?? "Unexpected error. Nothing was changed."];
  return ["Request failed", error?.message ?? "Unexpected error."];
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
  submitButton.disabled =
    commandInFlight || !hasProjection || !allowedActions.includes(operationInput.value);
}

function clearActionProjection() {
  contextAlertId = "";
  allowedActions = null;
  actionsStatus.textContent = sessionActive
    ? "Loading operations permitted by the backend…"
    : "Connect and select an alert to load actions from the backend.";
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
    clearResultDisplay("No recorded decision for this alert.");
    stateLine.textContent = `Alert ${alertId} has no recorded decision yet.`;
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
    link.href = `/public/incident-ui/war-room.html?incident_id=${encodeURIComponent(incident)}`;
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
      `Recovered from backend: ${text(item.status)}` + (incident === "" ? "." : `, incident ${incident}.`);
    stateLine.textContent =
      `Alert ${alertInput.value.trim()} is ${text(item.status)} (version ${String(item.expected_version)}), read from the API.`;
  } else {
    resultSummary.textContent =
      `${operation} applied: ${text(item.status)}` + (incident === "" ? "." : `, incident ${incident}.`);
    stateLine.textContent =
      `Alert ${alertInput.value.trim()} is ${text(item.status)} (version ${String(item.expected_version)}).`;
  }
  announce(resultSummary.textContent);
}

function clearResult() {
  clearResultDisplay("No command sent yet.");
  stateLine.textContent = "Connect to begin.";
  versionInput.value = "1";
  alertInput.value = "";
  reasonInput.value = "";
  targetInput.value = "";
  severityInput.value = "";
  impactInput.value = "";
  lastObservedAlertId = "";
}

const OPERATION_FIELDS = Object.freeze({
  open_triage: Object.freeze([]),
  triage_dismiss: Object.freeze(["reason"]),
  triage_link: Object.freeze(["reason", "target_incident_id"]),
  triage_declare: Object.freeze(["reason", "severity", "impact"]),
});

function buildBody(operation) {
  const versionText = versionInput.value.trim();
  const version = versionText === "" ? Number.NaN : Number(versionText);
  if (!Number.isInteger(version) || version < 1)
    return { ok: false, message: "Enter the expected version from the current state." };
  const fields = OPERATION_FIELDS[operation];
  if (fields === undefined)
    return { ok: false, message: "Select a supported operation." };
  const body = { operation, expected_version: version };
  const reason = reasonInput.value.trim();
  if (reason !== "" && fields.includes("reason")) body.reason = reason;
  const target = targetInput.value.trim();
  if (target !== "" && fields.includes("target_incident_id")) body.target_incident_id = target;
  const severity = severityInput.value;
  if (severity !== "" && fields.includes("severity")) body.severity = severity;
  const impact = impactInput.value;
  impactInput.setAttribute("aria-required", String(fields.includes("impact")));
  if (fields.includes("impact")) {
    if (impact.trim() === "")
      return { ok: false, message: "Impact is required when declaring an incident." };
    if (impact.length > 2000)
      return { ok: false, message: "Impact must be no more than 2000 characters." };
    body.impact = impact;
  }
  return { ok: true, body };
}

async function readTriageContext(
  alertId,
  generation,
  { preserveResult = false, confirmedCommand = false, showReadError = true } = {},
) {
  const requestGeneration = ++contextGeneration;
  contextAlertId = "";
  allowedActions = null;
  actionsStatus.textContent = "Loading operations permitted by the backend…";
  updateActionControls();
  page.dataset.state = "loading";
  try {
    const item = await controlApi.getTriageContext(alertId);
    if (
      generation !== sessionGeneration || requestGeneration !== contextGeneration ||
      alertInput.value.trim() !== alertId || !sessionActive
    ) return { ok: false, stale: true };
    if (!isValidContext(item, alertId)) {
      throw new ApiClientError("invalid_response", "The API returned an invalid triage context.");
    }
    if (confirmedCommand && item.triage_state === null) {
      contextAlertId = "";
      allowedActions = null;
      actionsStatus.textContent = "The command result is confirmed, but no triage state was returned; further operations are disabled.";
      updateActionControls();
      page.dataset.state = "error";
      const error = new ApiClientError(
        "invalid_response",
        "The command was confirmed, but backend context contains no triage state. Further operations are disabled.",
      );
      stateLine.textContent = "The command result is confirmed; current operations are unavailable.";
      if (showReadError) showError(error, "read");
      return { ok: false, error };
    }
    contextAlertId = alertId;
    allowedActions = [...item.allowed_actions];
    actionsStatus.textContent = allowedActions.length === 0
      ? "The backend currently permits no triage operations for this alert."
      : "Enabled operations are permitted by the backend for this identity and alert.";
    updateActionControls();
    renderContextState(alertId, item.triage_state);
    page.dataset.state = "ready";
    hideError();
    return { ok: true, item };
  } catch (error) {
    if (
      generation !== sessionGeneration || requestGeneration !== contextGeneration ||
      alertInput.value.trim() !== alertId || !sessionActive
    ) return { ok: false, stale: true };
    contextAlertId = "";
    allowedActions = null;
    actionsStatus.textContent = preserveResult
      ? "The command result is confirmed; permitted next operations could not be refreshed."
      : "No operation is available until backend context can be read.";
    updateActionControls();
    if (!preserveResult) clearResultDisplay("Current state could not be verified; no command was confirmed.");
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    if (preserveResult) {
      stateLine.textContent = "The command result is confirmed; current operations are unavailable.";
    } else {
      stateLine.textContent = `Alert ${alertId} current state is unavailable.`;
    }
    if (showReadError) showError(error, "read");
    return { ok: false, error };
  }
}

async function refreshAfterConflict(alertId, generation) {
  const refreshed = await readTriageContext(alertId, generation, { showReadError: false });
  if (refreshed.stale) return;
  if (refreshed.ok) {
    page.dataset.state = "error";
    showError({
      kind: "conflict",
      message: "The command version is stale. Current API state is shown; review the command context and submit again.",
    });
  } else {
    const readError = refreshed.error;
    const [readTitle, readDetail] = describeError(readError, "read");
    clearResultDisplay("Current state could not be verified; no command was confirmed.");
    showError({
      kind: "conflict",
      message: `The command version is stale. Current state could not be refreshed (${readTitle}: ${readDetail}). No command was retried or confirmed.`,
    });
  }
}

async function sendCommand() {
  if (commandInFlight) return;
  const alertId = alertInput.value.trim();
  if (alertId === "") {
    showError({ kind: "validation", message: "Enter an alert identifier." });
    return;
  }
  const operation = operationInput.value;
  if (contextAlertId !== alertId || !allowedActions?.includes(operation)) {
    showError({ kind: "validation", message: "Select an operation currently permitted by the backend." });
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
  announce(`Sending ${operation}.`);
  try {
    const item = await controlApi.postTriageCommand(alertId, checked.body, idempotencyKey);
    if (generation !== sessionGeneration) return;
    page.dataset.state = "ready";
    setResult(operation, item ?? {});
    const url = new URL(window.location.href);
    url.searchParams.set("alert_id", alertId);
    window.history.replaceState(null, "", url);
    await readTriageContext(alertId, generation, { preserveResult: true, confirmedCommand: true });
  } catch (error) {
    if (generation !== sessionGeneration) return;
    if (error?.kind === "conflict" && error?.code === "stale_version") {
      await refreshAfterConflict(alertId, generation);
    } else {
      if (error?.kind === "authorization") {
        contextGeneration += 1;
        clearActionProjection();
        actionsStatus.textContent = "The command was denied; reload backend permissions before retrying.";
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
  impactInput.setAttribute(
    "aria-required",
    String(OPERATION_FIELDS[operationInput.value]?.includes("impact") ?? false),
  );
  hideError();
  updateActionControls();
});

alertInput.addEventListener("input", () => {
  const alertId = alertInput.value.trim();
  if (alertId === lastObservedAlertId) return;
  lastObservedAlertId = alertId;
  contextGeneration += 1;
  clearActionProjection();
  clearResultDisplay("Loading current alert context from the backend.");
  versionInput.value = "1";
  if (!sessionActive) return;
  hideError();
  if (!/^[a-z][a-z0-9_-]{2,63}$/.test(alertId)) {
    actionsStatus.textContent = "Enter a valid alert identifier to load backend-permitted operations.";
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
    showError({ kind: "validation", message: "Enter an alert identifier." }, "read");
    return;
  }
  hideError();
  announce("Loading alert triage context and backend-authorized operations.");
  return readTriageContext(alertId, sessionGeneration);
}

sessionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = apiKeyInput.value.trim();
  if (!value) {
    showError({ kind: "validation", message: "Enter an API key." });
    return;
  }
  credentialStore.set(value);
  apiKeyInput.value = "";
  sessionGeneration += 1;
  sessionActive = true;
  contextGeneration += 1;
  commandInFlight = false;
  alertInput.disabled = false;
  clearActionProjection();
  const deepLinkAlertId = pendingDeepLinkAlertId;
  pendingDeepLinkAlertId = "";
  clearResult();
  if (deepLinkAlertId !== "") alertInput.value = deepLinkAlertId;
  lastObservedAlertId = alertInput.value.trim();
  hideError();
  page.dataset.state = "idle";
  stateLine.textContent = "Connected. Enter an alert and send a command.";
  announce("Session set.");
  const alertId = alertInput.value.trim();
  if (alertId !== "") recoverDecision(alertId);
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  credentialStore.clear();
  sessionActive = false;
  contextGeneration += 1;
  commandInFlight = false;
  alertInput.disabled = false;
  clearActionProjection();
  hideError();
  page.dataset.state = "idle";
  clearResult();
  pendingDeepLinkAlertId = "";
  const url = new URL(window.location.href);
  url.searchParams.delete("alert_id");
  window.history.replaceState(null, "", url);
  announce("Session cleared.");
});

const initialAlertId = new URL(window.location.href).searchParams.get("alert_id") ?? "";
if (/^[a-z][a-z0-9_-]{2,63}$/.test(initialAlertId)) alertInput.value = initialAlertId;
lastObservedAlertId = alertInput.value.trim();
let pendingDeepLinkAlertId = /^[a-z][a-z0-9_-]{2,63}$/.test(initialAlertId) ? initialAlertId : "";

page.dataset.state = "idle";
clearActionProjection();
