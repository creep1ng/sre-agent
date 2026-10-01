import {
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const page = document.getElementById("consumption-page");
const sessionForm = document.getElementById("session-form");
const apiKeyInput = document.getElementById("api-key");
const liveRegion = document.getElementById("live-region");
const errorBox = document.getElementById("page-error");
const errorTitle = document.getElementById("page-error-title");
const errorDetail = document.getElementById("page-error-detail");
const queryForm = document.getElementById("query-form");
const disconnectButton = document.getElementById("disconnect-button");
const loadingState = document.getElementById("result-loading");
const statusLine = document.getElementById("result-status");
const scopeNote = document.getElementById("result-scope-note");
const resultList = document.getElementById("result-list");
const monthNote = document.getElementById("result-month-note");
const monthValue = document.getElementById("summary-month");
const fields = {
  requestCount: document.getElementById("summary-request-count"),
  incidentRuns: document.getElementById("summary-incident-runs"),
  inputTokens: document.getElementById("summary-input-tokens"),
  outputTokens: document.getElementById("summary-output-tokens"),
  totalTokens: document.getElementById("summary-total-tokens"),
  cost: document.getElementById("summary-cost"),
  costProvenance: document.getElementById("summary-cost-provenance"),
  coverage: document.getElementById("summary-coverage"),
};
const filters = {
  request: {
    button: document.getElementById("filter-request"),
    field: document.getElementById("field-request"),
    input: document.getElementById("request-id"),
  },
  incident: {
    button: document.getElementById("filter-incident"),
    field: document.getElementById("field-incident"),
    input: document.getElementById("incident-id"),
  },
  month: {
    button: document.getElementById("filter-month"),
    field: document.getElementById("field-month"),
    input: document.getElementById("consumption-month"),
  },
};

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let activeFilter = "request";
let sessionGeneration = 0;

const announce = (message) => {
  liveRegion.textContent = message;
};
// Authoritative rendering only: null stays unavailable, never zero;
// non-null values are shown verbatim with no frontend math.
const textOf = (value) => (value === null || value === undefined ? "Unavailable" : String(value));

function describeError(error) {
  if (error?.kind === "network")
    return ["API unavailable", "The control-plane API could not be reached. Check the stack and retry."];
  if (error?.status === 401)
    return ["Authentication required", "Provide a valid API key. Nothing else is confirmed."];
  if (error?.status === 403)
    return ["Access unavailable", "Consumption cannot be confirmed for this identity. Nothing else is revealed."];
  if (error?.status === 422)
    return ["Choose exactly one valid filter", "Provide exactly one request, incident, or month value."];
  if (error?.status === 413)
    return ["Scope too large", "The matching evidence exceeds the projection bound. Narrow the scope."];
  if (error?.status === 503)
    return ["Consumption unavailable", "Persisted usage could not be read. No empty result is substituted."];
  return ["Request failed", error?.message ?? "Unexpected error."];
}

function hideError() {
  errorBox.hidden = true;
  errorTitle.textContent = "";
  errorDetail.textContent = "";
}

function showError(title, detail) {
  errorTitle.textContent = title;
  errorDetail.textContent = detail;
  errorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function clearResult() {
  loadingState.hidden = true;
  resultList.hidden = true;
  scopeNote.hidden = true;
  monthNote.hidden = true;
  statusLine.textContent = "Choose a filter and load consumption.";
}

function setActiveFilter(name) {
  activeFilter = name;
  for (const [key, filter] of Object.entries(filters)) {
    const selected = key === name;
    filter.button.setAttribute("aria-pressed", String(selected));
    filter.field.hidden = !selected;
    if (!selected) filter.input.value = "";
  }
  hideError();
  clearResult();
  page.dataset.state = "idle";
  announce(`Filter: ${name}. Previous input and result cleared.`);
}

function renderSummary(payload, selectorValue) {
  const totals = payload?.totals ?? {};
  const cost = totals.cost ?? {};
  const coverage = payload?.coverage ?? {};
  const costMissing = cost.amount === null || cost.amount === undefined;
  fields.requestCount.textContent = textOf(payload?.request_count);
  fields.incidentRuns.textContent = textOf(payload?.incident_runs);
  fields.inputTokens.textContent = textOf(totals.input_tokens);
  fields.outputTokens.textContent = textOf(totals.output_tokens);
  fields.totalTokens.textContent = textOf(totals.total_tokens);
  fields.cost.textContent = costMissing ? "Cost unavailable" : `${cost.amount} USD / Billed · exact`;
  const versions = Array.isArray(cost.price_versions)
    ? cost.price_versions.filter((version) => typeof version === "string")
    : [];
  fields.costProvenance.textContent =
    versions.length === 0
      ? "—"
      : `Price versions: ${versions.join(", ")}${costMissing ? " (no combinable total)" : ""}`;
  const status = typeof coverage.status === "string" ? coverage.status : "unknown";
  fields.coverage.textContent =
    `${status} — known ${textOf(coverage.known)}, incomplete ${textOf(coverage.incomplete)}, unknown ${textOf(coverage.unknown)}`;
  scopeNote.hidden = !(payload?.request_count === 0 && coverage.status === "complete");
  if (activeFilter === "month") {
    monthValue.textContent = selectorValue;
    monthNote.hidden = false;
  } else {
    monthNote.hidden = true;
  }
  loadingState.hidden = true;
  resultList.hidden = false;
  statusLine.textContent = "Consumption loaded.";
  page.dataset.state = "ready";
  announce(scopeNote.hidden ? "Consumption loaded." : "No consumption evidence in this scope.");
}

for (const [name, filter] of Object.entries(filters)) {
  filter.button.addEventListener("click", () => setActiveFilter(name));
}

sessionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = apiKeyInput.value.trim();
  if (!value) {
    errorTitle.textContent = "Enter an API key.";
    errorDetail.textContent = "";
    errorBox.hidden = false;
    announce("Enter an API key.");
    return;
  }
  credentialStore.set(value);
  apiKeyInput.value = "";
  announce("Session set. Choose a filter and load consumption.");
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  credentialStore.clear();
  hideError();
  clearResult();
  page.dataset.state = "idle";
  announce("Session cleared.");
});

queryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const generation = sessionGeneration + 1;
  sessionGeneration = generation;
  hideError();
  resultList.hidden = true;
  scopeNote.hidden = true;
  monthNote.hidden = true;
  loadingState.hidden = false;
  statusLine.textContent = "Loading consumption…";
  page.dataset.state = "loading";
  announce("Loading consumption.");
  const value = filters[activeFilter].input.value.trim();
  if (!value) {
    if (generation !== sessionGeneration) return;
    loadingState.hidden = true;
    statusLine.textContent = "Choose a filter and load consumption.";
    page.dataset.state = "idle";
    showError("Choose exactly one valid filter", "Enter a value for the selected filter.");
    return;
  }
  try {
    const selector =
      activeFilter === "request"
        ? { requestId: value }
        : activeFilter === "incident"
          ? { incidentId: value }
          : { month: value };
    const payload = await controlApi.readUsageConsumption(selector);
    if (generation !== sessionGeneration) return;
    renderSummary(payload, value);
  } catch (error) {
    if (generation !== sessionGeneration) return;
    loadingState.hidden = true;
    resultList.hidden = true;
    scopeNote.hidden = true;
    monthNote.hidden = true;
    statusLine.textContent = "Not loaded.";
    page.dataset.state = "error";
    const [title, detail] = describeError(error);
    showError(title, detail);
  }
});

page.dataset.state = "idle";
