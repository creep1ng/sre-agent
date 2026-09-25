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

function describeError(error) {
  if (error?.kind === "network")
    return ["API unavailable", "The triage API could not be reached. Check the stack and retry."];
  if (error?.kind === "authentication")
    return ["Authentication required", "Provide a valid API key. Nothing else is confirmed."];
  if (error?.kind === "authorization")
    return ["Access unavailable", "The command cannot be confirmed for this identity."];
  if (error?.kind === "not_found")
    return ["Not found", "Unknown alert or target incident. Nothing was changed."];
  if (error?.kind === "conflict")
    return ["Conflict", "The version is stale or the command key was reused. Refresh state."];
  if (error?.kind === "api" && error?.status === 422)
    return ["Invalid request", error?.message ?? "The command payload was rejected."];
  if (error?.kind === "api" && error?.code === "audit_unavailable")
    return ["Service unavailable", error?.message ?? "The request was not completed. Retry."];
  if (error?.kind === "api")
    return ["Request failed", error?.message ?? "Unexpected error. Nothing was changed."];
  return ["Request failed", error?.message ?? "Unexpected error."];
}

function showError(error) {
  const [title, detail] = describeError(error);
  errorTitle.textContent = title;
  errorDetail.textContent = detail;
  errorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function hideError() {
  errorBox.hidden = true;
  errorDetail.textContent = "";
}

function setResult(operation, item) {
  resultOperation.textContent = operation;
  resultStatus.textContent = text(item.status) || "—";
  resultIncident.textContent = text(item.incident_id) || "—";
  resultVersion.textContent = item.expected_version === undefined ? "—" : String(item.expected_version);
  resultActor.textContent = text(item.actor) || "—";
  resultDecided.textContent = text(item.decided_at) || "—";
  versionInput.value = item.expected_version === undefined ? versionInput.value : String(item.expected_version);
  const incident = text(item.incident_id);
  resultSummary.textContent =
    `${operation} applied: ${text(item.status)}` + (incident === "" ? "." : `, incident ${incident}.`);
  stateLine.textContent =
    `Alert ${alertInput.value.trim()} is ${text(item.status)} (version ${String(item.expected_version)}).`;
  announce(resultSummary.textContent);
}

function buildBody(operation) {
  const versionText = versionInput.value.trim();
  const version = versionText === "" ? Number.NaN : Number(versionText);
  if (!Number.isInteger(version) || version < 1)
    return { ok: false, message: "Enter the expected version from the current state." };
  const body = { operation, expected_version: version };
  const reason = reasonInput.value.trim();
  if (reason !== "") body.reason = reason;
  const target = targetInput.value.trim();
  if (target !== "") body.target_incident_id = target;
  const severity = severityInput.value;
  if (severity !== "") body.severity = severity;
  return { ok: true, body };
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
  } catch (error) {
    if (generation !== sessionGeneration) return;
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    showError(error);
  } finally {
    commandInFlight = false;
    submitButton.disabled = false;
  }
}

commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCommand();
});

sessionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = apiKeyInput.value.trim();
  if (!value) {
    showError({ kind: "validation", message: "Enter an API key." });
    return;
  }
  credentialStore.set(value);
  apiKeyInput.value = "";
  hideError();
  page.dataset.state = "idle";
  stateLine.textContent = "Connected. Enter an alert and send a command.";
  announce("Session set.");
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  credentialStore.clear();
  commandInFlight = false;
  submitButton.disabled = false;
  hideError();
  page.dataset.state = "idle";
  stateLine.textContent = "Connect to begin.";
  resultSummary.textContent = "No command sent yet.";
  announce("Session cleared.");
});

page.dataset.state = "idle";
