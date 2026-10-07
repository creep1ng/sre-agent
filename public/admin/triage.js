import {
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
const submitButton = document.getElementById("submit-button");
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

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let sessionGeneration = 0;
let commandInFlight = false;

const text = (value) => (typeof value === "string" ? value : "");
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
  resultSummary.textContent = summary;
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
}

const OPERATION_FIELDS = Object.freeze({
  open_triage: Object.freeze([]),
  triage_dismiss: Object.freeze(["reason"]),
  triage_link: Object.freeze(["reason", "target_incident_id"]),
  triage_declare: Object.freeze(["reason", "severity"]),
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
  return { ok: true, body };
}

async function refreshAfterConflict(alertId, generation) {
  try {
    const item = await controlApi.getTriageState(alertId);
    if (generation !== sessionGeneration) return;
    page.dataset.state = "error";
    setResult(item.status ?? "read", item ?? {}, "recovered");
    showError({
      kind: "conflict",
      message: "The command version is stale. Current API state is shown; review the command context and submit again.",
    });
  } catch (readError) {
    if (generation !== sessionGeneration) return;
    const [readTitle, readDetail] = describeError(readError, "read");
    page.dataset.state = readError?.kind === "network" ? "offline" : "error";
    clearResultDisplay("Current state could not be verified; no command was confirmed.");
    stateLine.textContent = `Alert ${alertId} current state is unavailable.`;
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
  const checked = buildBody(operation);
  if (!checked.ok) {
    showError({ kind: "validation", message: checked.message });
    return;
  }
  const generation = sessionGeneration;
  const idempotencyKey = newCommandKey();
  commandInFlight = true;
  submitButton.disabled = true;
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
  } catch (error) {
    if (generation !== sessionGeneration) return;
    if (error?.kind === "conflict" && error?.code === "stale_version") {
      await refreshAfterConflict(alertId, generation);
    } else {
      page.dataset.state = error?.kind === "network" ? "offline" : "error";
      showError(error);
    }
  } finally {
    if (generation === sessionGeneration) {
      commandInFlight = false;
      submitButton.disabled = false;
    }
  }
}

commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCommand();
});

operationInput.addEventListener("change", () => {
  hideError();
});

async function recoverDecision(alertId) {
  if (!/^[a-z][a-z0-9_-]{2,63}$/.test(alertId)) {
    showError({ kind: "validation", message: "Enter an alert identifier." }, "read");
    return;
  }
  const generation = sessionGeneration;
  commandInFlight = true;
  submitButton.disabled = true;
  hideError();
  page.dataset.state = "loading";
  announce("Recovering the persisted decision from the API.");
  try {
    const item = await controlApi.getTriageState(alertId);
    if (generation !== sessionGeneration) return;
    page.dataset.state = "ready";
    setResult(item.status ?? "read", item ?? {}, "recovered");
  } catch (error) {
    if (generation !== sessionGeneration) return;
    if (error?.kind === "not_found" && error?.code === "triage_not_found") {
      page.dataset.state = "ready";
      resultSummary.textContent = "No recorded decision for this alert.";
      stateLine.textContent = `Alert ${alertId} has no recorded decision yet.`;
      announce(resultSummary.textContent);
      return;
    }
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    showError(error, "read");
  } finally {
    if (generation === sessionGeneration) {
      commandInFlight = false;
      submitButton.disabled = false;
    }
  }
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
  commandInFlight = false;
  submitButton.disabled = false;
  const deepLinkAlertId = pendingDeepLinkAlertId;
  pendingDeepLinkAlertId = "";
  clearResult();
  if (deepLinkAlertId !== "") alertInput.value = deepLinkAlertId;
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
  commandInFlight = false;
  submitButton.disabled = false;
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
let pendingDeepLinkAlertId = /^[a-z][a-z0-9_-]{2,63}$/.test(initialAlertId) ? initialAlertId : "";

page.dataset.state = "idle";
