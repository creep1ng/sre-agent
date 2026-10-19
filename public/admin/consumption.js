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
const requestDetailStatus = document.getElementById("request-detail-status");
const requestDetailLoading = document.getElementById("request-detail-loading");
const requestDetailEmpty = document.getElementById("request-detail-empty");
const requestDetailList = document.getElementById("request-detail-list");
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

const limits = {
  status: document.getElementById("limits-status"),
  current: document.getElementById("limits-current"),
  version: document.getElementById("limits-version"),
  incident: document.getElementById("limits-incident"),
  monthly: document.getElementById("limits-monthly"),
  updated: document.getElementById("limits-updated"),
  form: document.getElementById("limits-form"),
  incidentInput: document.getElementById("limits-incident-input"),
  monthlyInput: document.getElementById("limits-monthly-input"),
  submit: document.getElementById("limits-submit"),
};
// Contract bounds of PUT /v1/consumption-limits; tokens stay below 2^53 so they are sent exactly.
const TOKENS_PATTERN = /^(?:0|[1-9][0-9]{0,14})$/;
const USD_PATTERN = /^(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,12})?$/;

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let activeFilter = "request";
let sessionGeneration = 0;
let limitsGeneration = 0;
let limitsPolicy = null;
let limitsPending = null;

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
  clearRequestDetail("Load consumption to see request detail.");
}

function clearRequestDetail(message) {
  requestDetailLoading.hidden = true;
  requestDetailList.hidden = true;
  requestDetailEmpty.hidden = true;
  requestDetailList.replaceChildren();
  if (typeof message === "string") requestDetailStatus.textContent = message;
}

// Contract 2.8.0 readUsageRequests allow-list only. No HMAC joins, no
// prompt/output/headers/credentials, no incident/run links: navigation is
// always { status: "unsupported" } per contract, so links are never rendered.
// Null stays unavailable; no arithmetic, pricing, or temporal grouping here.
function consumptionLine(consumption) {
  if (consumption === null || consumption === undefined) return "Consumption unavailable";
  const parts = [
    `availability ${textOf(consumption.availability)}`,
    `source ${textOf(consumption.source)}`,
    `input ${textOf(consumption.input_tokens)}`,
    `output ${textOf(consumption.output_tokens)}`,
    `total ${textOf(consumption.total_tokens)}`,
  ];
  const billedMissing = consumption.billed_usd === null || consumption.billed_usd === undefined;
  parts.push(billedMissing ? "Billed unavailable" : `Billed ${consumption.billed_usd} USD / exact`);
  const pricing = consumption.pricing_context;
  if (pricing !== null && pricing !== undefined) {
    parts.push(`price ${textOf(pricing.price_version)} @ ${textOf(pricing.observed_at)}`);
  }
  return parts.join(" · ");
}

function attributionNote(status) {
  if (status === "legacy")
    return "Historical unavailable — no verifiable history (never reconstructed from current assignment).";
  if (status === "unavailable")
    return "Unavailable — no attribution snapshot (rejected before provider invocation).";
  if (status === "partial") return "Partial — requested attribution is available; credited attribution is incomplete.";
  return "Available — immutable snapshot as published.";
}

function renderRequestDetail(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  requestDetailLoading.hidden = true;
  requestDetailList.replaceChildren();
  if (items.length === 0) {
    requestDetailList.hidden = true;
    requestDetailEmpty.hidden = false;
    requestDetailStatus.textContent = "No request detail in this scope.";
    announce("No request detail in this scope.");
    return;
  }
  for (const item of items) {
    const row = document.createElement("li");
    row.setAttribute("data-request-row", String(item?.request_id ?? ""));
    const title = document.createElement("p");
    title.className = "ma-mono";
    title.textContent = `Request ${textOf(item?.request_id)} · ${textOf(item?.month)} · ${textOf(item?.attribution_status)}`;
    row.appendChild(title);
    const note = document.createElement("p");
    note.className = "ma-panel__description";
    note.textContent = attributionNote(item?.attribution_status);
    note.setAttribute("data-attribution-note", String(item?.attribution_status ?? ""));
    row.appendChild(note);
    const requested = item?.requested_assignment ?? {};
    const requestedLine = document.createElement("p");
    requestedLine.className = "ma-mono";
    requestedLine.setAttribute("data-requested-assignment", requested.availability ?? "");
    requestedLine.textContent =
      requested.availability === "available"
        ? `Alias ${textOf(requested.alias)} · Model ${textOf(requested.model)} · Provider ${textOf(requested.provider)} · Router ${textOf(requested.router)}`
        : `Requested ${textOf(requested.availability)}`;
    row.appendChild(requestedLine);
    const creditedModel = item?.credited_model ?? {};
    const creditedProvider = item?.credited_provider ?? {};
    const creditedLine = document.createElement("p");
    creditedLine.className = "ma-mono";
    creditedLine.setAttribute("data-credited", `${creditedModel.availability ?? ""}/${creditedProvider.availability ?? ""}`);
    creditedLine.textContent = `Credited model ${textOf(creditedModel.value)} (${textOf(creditedModel.availability)}) · provider ${textOf(creditedProvider.value)} (${textOf(creditedProvider.availability)})`;
    row.appendChild(creditedLine);
    const consumption = document.createElement("p");
    consumption.className = "ma-mono";
    consumption.setAttribute("data-consumption", String(item?.consumption === null ? "unavailable" : "present"));
    consumption.textContent = consumptionLine(item?.consumption ?? null);
    row.appendChild(consumption);
    const navigation = document.createElement("p");
    navigation.className = "ma-panel__description";
    navigation.setAttribute("data-navigation", "unsupported");
    navigation.textContent = "Navigation unsupported — no incident or run links per contract.";
    row.appendChild(navigation);
    requestDetailList.appendChild(row);
  }
  requestDetailList.hidden = false;
  requestDetailEmpty.hidden = true;
  requestDetailStatus.textContent = `Request detail loaded: ${items.length} bounded request${items.length === 1 ? "" : "s"}.`;
  announce(requestDetailStatus.textContent);
}

function setActiveFilter(name) {
  sessionGeneration += 1;
  activeFilter = name;
  for (const [key, filter] of Object.entries(filters)) {
    const selected = key === name;
    filter.button.setAttribute("aria-pressed", String(selected));
    filter.field.hidden = !selected;
    if (!selected) filter.input.value = "";
  }
  hideError();
  clearResult();
  clearRequestDetail("Load consumption to see request detail.");
  page.dataset.state = "idle";
  announce(`Filter: ${name}. Previous input and result cleared.`);
}

function renderSummary(payload, requestFilter, selectorValue) {
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
  const authoritativeMonth =
    payload?.filter && typeof payload.filter.month === "string" ? payload.filter.month : null;
  if (authoritativeMonth !== null) {
    monthValue.textContent = authoritativeMonth;
    monthNote.hidden = false;
  } else if (requestFilter === "month") {
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

// The policy shown is always the server's answer: null is "Not configured", 0 is a real limit.
function renderLimits(policy, message) {
  limitsPolicy = policy;
  const shown = (value) => (value === null || value === undefined ? "Not configured" : String(value));
  limits.version.textContent = shown(policy.version);
  limits.incident.textContent = shown(policy.incident_token_limit);
  limits.monthly.textContent = shown(policy.monthly_usd_limit);
  limits.updated.textContent = shown(policy.updated_at);
  limits.incidentInput.value = policy.incident_token_limit === null ? "" : String(policy.incident_token_limit);
  limits.monthlyInput.value = policy.monthly_usd_limit === null ? "" : String(policy.monthly_usd_limit);
  limits.current.hidden = false;
  limits.form.hidden = false;
  limits.submit.disabled = false;
  limits.status.textContent = message;
}

function clearLimits(message) {
  limitsGeneration += 1;
  limitsPolicy = null;
  limitsPending = null;
  limits.current.hidden = true;
  limits.form.hidden = true;
  limits.status.textContent = message;
}

async function loadLimits(message) {
  clearLimits("Loading the consumption policy…");
  const generation = limitsGeneration;
  try {
    const policy = await controlApi.getConsumptionLimits();
    if (generation !== limitsGeneration) return;
    renderLimits(policy, message ?? `Policy version ${policy.version} applies to new gateway admissions.`);
  } catch (error) {
    if (generation !== limitsGeneration) return;
    limits.status.textContent = `Consumption limits unavailable: ${describeError(error)[0]}.`;
  }
}

limits.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!limitsPolicy || limits.submit.disabled) return;
  const tokens = limits.incidentInput.value.trim();
  const usd = limits.monthlyInput.value.trim();
  if ((tokens && !TOKENS_PATTERN.test(tokens)) || (usd && !USD_PATTERN.test(usd))) {
    limits.status.textContent = "Invalid limits: use a whole number of tokens and a USD amount with up to 12 decimals, or leave empty. Nothing was sent.";
    return;
  }
  const body = {
    expected_version: limitsPolicy.version,
    incident_token_limit: tokens ? Number(tokens) : null,
    monthly_usd_limit: usd || null,
  };
  const bodyKey = JSON.stringify(body);
  if (limitsPending?.bodyKey !== bodyKey) {
    // getRandomValues works on plain-HTTP origins too (randomUUID needs a secure context).
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    limitsPending = { bodyKey, key: `limits-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}` };
  }
  const generation = limitsGeneration;
  limits.submit.disabled = true;
  limits.status.textContent = "Saving the consumption policy…";
  try {
    const policy = await controlApi.replaceConsumptionLimits(body, limitsPending.key);
    if (generation !== limitsGeneration) return;
    limitsPending = null;
    renderLimits(policy, `Saved: policy version ${policy.version} applies to new gateway admissions.`);
    announce(limits.status.textContent);
  } catch (error) {
    if (generation !== limitsGeneration) return;
    limits.submit.disabled = false;
    if (error?.status === 409) {
      limitsPending = null;
      await loadLimits("The policy changed elsewhere (409). The current version is shown; nothing was overwritten.");
    } else if (error?.status === 422 || error?.status === 400) {
      limits.status.textContent = "Invalid limits (rejected by the API). The active policy is unchanged.";
    } else {
      limits.status.textContent = `Not saved: ${describeError(error)[0]}. The active policy is unchanged.`;
    }
    announce(limits.status.textContent);
  }
});

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
  sessionGeneration += 1;
  hideError();
  clearResult();
  clearRequestDetail("Load consumption to see request detail.");
  page.dataset.state = "idle";
  announce("Session set. Choose a filter and load consumption.");
  loadLimits();
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  credentialStore.clear();
  hideError();
  clearResult();
  clearRequestDetail("Load consumption to see request detail.");
  clearLimits("Connect to load the policy.");
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
  clearRequestDetail();
  requestDetailLoading.hidden = false;
  requestDetailStatus.textContent = "Loading request detail…";
  page.dataset.state = "loading";
  announce("Loading consumption.");
  const requestFilter = activeFilter;
  const value = filters[requestFilter].input.value.trim();
  if (!value) {
    if (generation !== sessionGeneration) return;
    loadingState.hidden = true;
    statusLine.textContent = "Choose a filter and load consumption.";
    clearRequestDetail("Load consumption to see request detail.");
    page.dataset.state = "idle";
    showError("Choose exactly one valid filter", "Enter a value for the selected filter.");
    return;
  }
  try {
    const selector =
      requestFilter === "request"
        ? { requestId: value }
        : requestFilter === "incident"
          ? { incidentId: value }
          : { month: value };
    const payload = await controlApi.readUsageConsumption(selector);
    if (generation !== sessionGeneration) return;
    renderSummary(payload, requestFilter, value);
    try {
      const detail = await controlApi.readUsageRequests(selector);
      if (generation !== sessionGeneration) return;
      renderRequestDetail(detail);
    } catch (detailError) {
      if (generation !== sessionGeneration) return;
      requestDetailLoading.hidden = true;
      requestDetailList.hidden = true;
      requestDetailEmpty.hidden = true;
      const [title, detailMessage] = describeError(detailError);
      requestDetailStatus.textContent = `${title}. ${detailMessage}`;
      announce(`Request detail: ${title}. ${detailMessage}`);
    }
  } catch (error) {
    if (generation !== sessionGeneration) return;
    loadingState.hidden = true;
    resultList.hidden = true;
    scopeNote.hidden = true;
    monthNote.hidden = true;
    statusLine.textContent = "Not loaded.";
    clearRequestDetail("Request detail not loaded.");
    page.dataset.state = "error";
    const [title, detail] = describeError(error);
    showError(title, detail);
  }
});

page.dataset.state = "idle";
