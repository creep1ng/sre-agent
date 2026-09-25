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

const text = (value) => (typeof value === "string" ? value : "");
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
  const rows = [["Event", eventId], ["Occurred", text(item.occurred_at)], ["Operation", text(item.operation)],
    ["Outcome", text(item.outcome)], ["Actor kind", text(identity.principal_kind)],
    ["Actor status", text(identity.principal_status)], ["Actor reference", text(identity.principal_ref?.digest)],
    ["Resource type", text(resource.resource_type)], ["Resource reference", text(resource.resource_ref?.digest)],
    ["Model alias reference", text(item.model_alias_ref?.digest)],
    ["Policy decision", text(decision.decision)], ["Content state", text(item.content_state)]];
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

async function loadEvents() {
  const generation = sessionGeneration + 1;
  sessionGeneration = generation;
  errorBox.hidden = true;
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
    renderRows();
    loadingState.hidden = true;
    if (currentItems.length > 0) {
      page.dataset.state = "ready";
      listWrap.hidden = false;
      countLine.textContent = `${currentItems.length} audit event${currentItems.length === 1 ? "" : "s"}.`;
      announce(countLine.textContent);
      return true;
    }
    page.dataset.state = "empty";
    listEmpty.hidden = false;
    emptyDetail.textContent = "The API returned an empty audit events list for these filters.";
    countLine.textContent = "No audit events.";
    announce("No audit events.");
    expanded.clear();
    return true;
  } catch (error) {
    if (generation !== sessionGeneration) return false;
    currentItems = [];
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
    const index = currentItems.findIndex((entry) => text(entry.event_id) === eventId);
    if (index >= 0) currentItems[index] = item;
    else currentItems = [...currentItems, item];
    expanded.add(eventId);
    renderRows();
  } catch (error) {
    if (generation !== sessionGeneration) return;
    showError(error);
    await loadEvents();
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
