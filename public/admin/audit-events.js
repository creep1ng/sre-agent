import { createAdministrativeApiClient, createMemoryCredentialStore } from "/public/api/client.js";

const page = document.getElementById("audit-events-page");
const sessionForm = document.getElementById("session-form");
const apiKeyInput = document.getElementById("api-key");
const filtersForm = document.getElementById("filters-form");
const liveRegion = document.getElementById("live-region");
const errorBox = document.getElementById("page-error");
const errorTitle = document.getElementById("page-error-title");
const errorDetail = document.getElementById("page-error-detail");
const loadingState = document.getElementById("list-loading");
const listWrap = document.getElementById("list-wrap");
const listEmpty = document.getElementById("list-empty");
const emptyDetail = document.getElementById("list-empty-detail");
const countLine = document.getElementById("event-count");
const rowsBody = document.getElementById("event-rows");
const disconnectButton = document.getElementById("disconnect-button");

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
const expanded = new Set();
let currentItems = [];
let currentFilters = {};
let sessionGeneration = 0;
const canonicalUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const text = (value) => (typeof value === "string" ? value : "");
const refDigest = (value) => (value && typeof value === "object" ? text(value.digest) : "");
const announce = (message) => {
  liveRegion.textContent = message;
};
function el(tag, cls, txt) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (txt !== undefined) node.textContent = txt;
  return node;
}

function describeError(error) {
  if (error?.kind === "network") return ["API unavailable", "The control-plane API could not be reached. Check the stack and retry."];
  if (error?.kind === "authentication") return ["Authentication required", "Provide a valid API key. Nothing else is confirmed."];
  if (error?.kind === "authorization") return ["Access unavailable", "The list cannot be confirmed for this identity. Nothing else is revealed."];
  if (error?.kind === "not_found") return ["Audit event not found", "The event is absent or hidden. The list was refreshed."];
  if (error?.kind === "api" && error?.code === "validation_error") return ["Invalid request", "Check the filters or the event identifier. Nothing was changed."];
  if (error?.kind === "api" && error?.code === "audit_unavailable") return ["Service unavailable", "The request was not completed. Refresh and retry."];
  return ["Request failed", error?.message ?? "Unexpected error."];
}

function showError(error) {
  const [title, detail] = describeError(error);
  errorTitle.textContent = title;
  errorDetail.textContent = detail;
  errorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function collectFilters() {
  const filters = {};
  for (const [key, value] of new FormData(filtersForm)) {
    const trimmed = String(value).trim();
    if (trimmed !== "") filters[key] = trimmed;
  }
  if (!filters.limit) filters.limit = "100";
  return filters;
}

function detailRow(item) {
  const eventId = text(item.event_id);
  const identity = item.identity && typeof item.identity === "object" ? item.identity : {};
  const resource = item.resource && typeof item.resource === "object" ? item.resource : {};
  const decision = item.policy_decision && typeof item.policy_decision === "object" ? item.policy_decision : {};
  const routing = item.routing && typeof item.routing === "object" ? item.routing : null;
  const correlation = item.correlation && typeof item.correlation === "object" ? item.correlation : {};
  const rows = [["Event", eventId], ["Occurred", text(item.occurred_at)], ["Operation", text(item.operation)],
    ["Outcome", text(item.outcome)],
    ["Response status", item.response_status === undefined ? "" : String(item.response_status)],
    ["Latency (ms)", item.latency_ms === undefined ? "" : String(item.latency_ms)],
    ["Actor kind", text(identity.principal_kind)],
    ["Actor status", text(identity.principal_status)], ["Actor reference", text(identity.principal_ref?.digest)],
    ["Resource type", text(resource.resource_type)], ["Resource reference", text(resource.resource_ref?.digest)],
    ["Model alias reference", text(item.model_alias_ref?.digest)], ["Router", routing === null ? "" : text(routing.router)],
    ["Model reference", text(routing?.model_ref?.digest)], ["Provider reference", text(routing?.provider_ref?.digest)],
    ["Policy decision", text(decision.decision)], ["Content state", text(item.content_state)],
    ["Request ID", text(correlation.request_id)], ["Incident reference", refDigest(correlation.incident_ref)],
    ["Run reference", refDigest(correlation.run_ref)], ["Task reference", refDigest(correlation.task_ref)],
    ["Trace reference", refDigest(correlation.trace_ref)]];
  const detail = el("tr", "principals__detail-row");
  detail.dataset.eventDetail = eventId;
  const cell = el("td");
  cell.colSpan = 5;
  const panel = el("div", "principals__detail");
  const list = el("dl", "principals__facts");
  for (const [term, value] of rows) {
    if (value === "") continue;
    list.append(el("dt", null, term), el("dd", "ma-mono", value));
  }
  panel.append(list);
  const rawRequestId = correlation.request_id;
  if (typeof rawRequestId === "string" && canonicalUuid.test(rawRequestId)) {
    const requestId = rawRequestId.toLowerCase();
    const href = new URL("/public/admin/audit-events.html", window.location.origin);
    href.searchParams.set("request_id", requestId);
    const link = el("a", "ma-button ma-button--secondary ma-button--small", "View correlated events");
    link.href = href.pathname + href.search;
    panel.append(link);
  }
  cell.append(panel);
  detail.append(cell);
  return detail;
}

function renderRows() {
  rowsBody.replaceChildren();
  for (const item of currentItems) {
    const eventId = text(item.event_id);
    const row = el("tr");
    row.dataset.eventRow = eventId;
    const code = el("code", "ma-mono", eventId.length > 13 ? `${eventId.slice(0, 13)}…` : eventId);
    const idCell = el("td");
    idCell.append(code);
    const badge = el("span", "ma-badge", text(item.outcome) || "unknown");
    badge.dataset.tone = item.outcome === "success" ? "success" : item.outcome === "denied" ? "warning" : "info";
    const outcomeCell = el("td");
    outcomeCell.append(badge);
    const toggle = el("button", "ma-button ma-button--ghost ma-button--small", expanded.has(eventId) ? "Hide" : "Details");
    toggle.type = "button";
    toggle.dataset.expandEvent = eventId;
    toggle.setAttribute("aria-expanded", String(expanded.has(eventId)));
    const actionCell = el("td");
    actionCell.append(toggle);
    row.append(idCell, el("td", "ma-mono", text(item.occurred_at) || "—"), outcomeCell,
      el("td", null, text(item.identity?.principal_kind) || "—"), actionCell);
    rowsBody.append(row);
    if (expanded.has(eventId)) rowsBody.append(detailRow(item));
  }
}

async function loadEvents({ preserveError = false } = {}) {
  const generation = sessionGeneration + 1;
  sessionGeneration = generation;
  if (!preserveError) errorBox.hidden = true;
  page.dataset.state = "loading";
  loadingState.hidden = false;
  listWrap.hidden = true;
  listEmpty.hidden = true;
  countLine.textContent = "Loading audit events…";
  announce("Loading audit events.");
  try {
    const payload = await controlApi.listAuditEvents(currentFilters);
    if (generation !== sessionGeneration) return false;
    currentItems = Array.isArray(payload?.items) ? payload.items : [];
    const truncated = payload?.truncated === true;
    renderRows();
    loadingState.hidden = true;
    if (currentItems.length > 0) {
      page.dataset.state = "ready";
      listWrap.hidden = false;
      countLine.textContent = `${currentItems.length} audit event${currentItems.length === 1 ? "" : "s"}.${truncated ? " Results are truncated; additional matching events were omitted." : ""}`;
      announce(countLine.textContent);
      return true;
    }
    page.dataset.state = "empty";
    listEmpty.hidden = false;
    emptyDetail.textContent = truncated
      ? "No audit events on this page. Additional matching events may be omitted because results are truncated."
      : "The API returned an empty audit events list for these filters.";
    countLine.textContent = truncated
      ? "No audit events on this page. Results are truncated; additional matching events may be omitted."
      : "No audit events.";
    announce(countLine.textContent);
    expanded.clear();
    return true;
  } catch (error) {
    if (generation !== sessionGeneration) return false;
    currentItems = [];
    expanded.clear();
    renderRows();
    loadingState.hidden = true;
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    listEmpty.hidden = false;
    emptyDetail.textContent = error?.kind === "authentication" ? "Provide a valid API key."
      : error?.kind === "network" ? "The list could not be loaded. Retry." : "The list cannot be confirmed for this identity.";
    countLine.textContent = "Not loaded.";
    showError(error);
    return false;
  }
}

rowsBody.addEventListener("click", async (event) => {
  const toggle = event.target.closest("[data-expand-event]");
  if (!toggle) return;
  const eventId = toggle.dataset.expandEvent;
  if (expanded.has(eventId)) {
    expanded.delete(eventId);
    renderRows();
    return;
  }
  const generation = sessionGeneration;
  try {
    const item = await controlApi.getAuditEvent(eventId);
    if (generation !== sessionGeneration) return;
    errorBox.hidden = true;
    const index = currentItems.findIndex((entry) => text(entry.event_id) === eventId);
    if (index >= 0) currentItems[index] = item;
    else currentItems = [...currentItems, item];
    expanded.add(eventId);
    renderRows();
  } catch (error) {
    if (generation !== sessionGeneration) return;
    showError(error);
    await loadEvents({ preserveError: true });
  }
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
  currentFilters = collectFilters();
  announce("Session set. Loading audit events.");
  loadEvents();
});

filtersForm.addEventListener("submit", (event) => {
  event.preventDefault();
  currentFilters = collectFilters();
  announce("Filters applied. Loading audit events.");
  loadEvents();
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  credentialStore.clear();
  expanded.clear();
  currentItems = [];
  renderRows();
  errorBox.hidden = true;
  loadingState.hidden = true;
  listWrap.hidden = true;
  listEmpty.hidden = false;
  emptyDetail.textContent = "Connect with an administrative API key and apply a filter to load the list.";
  countLine.textContent = "Not loaded.";
  page.dataset.state = "idle";
  announce("Session cleared.");
});

page.dataset.state = "idle";

function initializeRequestIdFilter() {
  const params = new URLSearchParams(window.location.search);
  const requestIds = params.getAll("request_id");
  if (window.location.search === "") return;

  const rawRequestId = requestIds.length === 1 && canonicalUuid.test(requestIds[0]) ? requestIds[0] : null;
  const requestId = rawRequestId?.toLowerCase() ?? null;
  if (requestId) document.getElementById("filter-request-id").value = requestId;

  // Keep only the one supported metadata filter in the address bar; never retain
  // accidental credentials, redirect targets, or arbitrary query state.
  const cleanUrl = new URL(window.location.pathname, window.location.origin);
  if (requestId) cleanUrl.searchParams.set("request_id", requestId);
  window.history.replaceState(null, "", cleanUrl.pathname + cleanUrl.search);
  if (requestIds.length > 0 && !requestId)
    showError({ kind: "validation", message: "The request ID link is invalid. Enter a valid request ID and apply filters." });
}

initializeRequestIdFilter();
