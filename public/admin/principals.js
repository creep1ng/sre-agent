import {
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const KINDS = new Set(["human", "agent"]);
const STATUSES = new Set(["active", "inactive"]);

const page = document.getElementById("principals-page");
const sessionForm = document.getElementById("session-form");
const apiKeyInput = document.getElementById("api-key");
const liveRegion = document.getElementById("live-region");
const errorBox = document.getElementById("page-error");
const errorTitle = document.getElementById("page-error-title");
const errorDetail = document.getElementById("page-error-detail");
const loadingState = document.getElementById("list-loading");
const listWrap = document.getElementById("list-wrap");
const listEmpty = document.getElementById("list-empty");
const emptyDetail = document.getElementById("list-empty-detail");
const countLine = document.getElementById("principal-count");
const rowsBody = document.getElementById("principal-rows");
const refreshButton = document.getElementById("refresh-button");
const disconnectButton = document.getElementById("disconnect-button");

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
const expanded = new Set();
let currentItems = [];
// Monotonic load generation: every loadPrincipals() call owns the UI until a
// newer load starts or the session is cleared. A late resolution from a
// previous generation (e.g. fetched with an older credential) must never
// render.
let sessionGeneration = 0;

const text = (value) => (typeof value === "string" ? value : "");
const known = (value, allowed) => (allowed.has(value) ? value : "unknown");
const announce = (message) => {
  liveRegion.textContent = message;
};

function hideError() {
  errorBox.hidden = true;
  errorDetail.textContent = "";
}

function describeError(error) {
  if (error?.kind === "network")
    return ["API unavailable", "The control-plane API could not be reached. Check the stack and retry."];
  if (error?.kind === "authentication")
    return ["Authentication required", "Provide a valid API key. Nothing else is confirmed."];
  if (error?.kind === "authorization" || error?.kind === "not_found")
    return ["Access unavailable", "The list cannot be confirmed for this identity. Nothing else is revealed."];
  if (error?.kind === "not_found")
    return ["Principal not found", "The principal is absent or hidden. The list was refreshed."];
  if (error?.kind === "conflict")
    return ["Resource changed", "Refresh and retry; nothing was overwritten."];
  return ["Request failed", error?.message ?? "Unexpected error."];
}

function showError(error) {
  const [title, detail] = describeError(error);
  errorTitle.textContent = title;
  errorDetail.textContent = detail;
  errorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function detailRow(item) {
  const principalId = text(item.principal_id);
  const detail = document.createElement("tr");
  detail.className = "principals__detail-row";
  detail.dataset.principalDetail = principalId;
  const cell = document.createElement("td");
  cell.colSpan = 5;
  const panel = document.createElement("div");
  panel.className = "principals__detail";
  const title = document.createElement("h3");
  title.textContent = text(item.display_name) || principalId;
  const list = document.createElement("dl");
  list.className = "principals__facts";
  for (const [term, value] of [
    ["Principal", principalId],
    ["Kind", known(item.kind, KINDS)],
    ["Status", known(item.status, STATUSES)],
    ["Created", text(item.created_at)],
    ["Updated", text(item.updated_at)],
  ]) {
    const name = document.createElement("dt");
    name.textContent = term;
    const data = document.createElement("dd");
    data.className = "ma-mono";
    data.textContent = value || "—";
    list.append(name, data);
  }
  panel.append(title, list);
  cell.append(panel);
  detail.append(cell);
  return detail;
}

function renderRows() {
  rowsBody.replaceChildren();
  for (const item of currentItems) {
    const principalId = text(item.principal_id);
    const row = document.createElement("tr");
    row.dataset.principalRow = principalId;
    const idCell = document.createElement("td");
    const code = document.createElement("code");
    code.className = "ma-mono";
    code.textContent = principalId;
    idCell.append(code);
    const kindCell = document.createElement("td");
    kindCell.textContent = known(item.kind, KINDS);
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "ma-badge";
    badge.dataset.tone = item.status === "active" ? "success" : item.status === "inactive" ? "warning" : "info";
    badge.textContent = known(item.status, STATUSES);
    statusCell.append(badge);
    const updatedCell = document.createElement("td");
    updatedCell.className = "ma-mono";
    updatedCell.textContent = text(item.updated_at);
    const actionCell = document.createElement("td");
    const toggle = document.createElement("button");
    toggle.className = "ma-button ma-button--ghost ma-button--small";
    toggle.type = "button";
    toggle.dataset.expandPrincipal = principalId;
    const isOpen = expanded.has(principalId);
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.textContent = isOpen ? "Hide" : "Details";
    actionCell.append(toggle);
    row.append(idCell, kindCell, statusCell, updatedCell, actionCell);
    rowsBody.append(row);
    if (isOpen) rowsBody.append(detailRow(item));
  }
}

async function loadPrincipals() {
  const generation = sessionGeneration + 1;
  sessionGeneration = generation;
  hideError();
  page.dataset.state = "loading";
  loadingState.hidden = false;
  listWrap.hidden = true;
  listEmpty.hidden = true;
  countLine.textContent = "Loading principals…";
  announce("Loading principals.");
  try {
    const payload = await controlApi.listPrincipals();
    if (generation !== sessionGeneration) return;
    currentItems = Array.isArray(payload?.items) ? payload.items : [];
    renderRows();
    loadingState.hidden = true;
    if (currentItems.length === 0) {
      page.dataset.state = "empty";
      listEmpty.hidden = false;
      emptyDetail.textContent = "The API returned an empty principals list.";
      countLine.textContent = "No principals.";
      announce("No principals.");
      return;
    }
    page.dataset.state = "ready";
    listWrap.hidden = false;
    countLine.textContent = `${currentItems.length} principal${currentItems.length === 1 ? "" : "s"}${payload?.truncated === true ? " (truncated)" : "."}`;
    announce(countLine.textContent);
  } catch (error) {
    if (generation !== sessionGeneration) return;
    loadingState.hidden = true;
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    listEmpty.hidden = false;
    emptyDetail.textContent =
      error?.kind === "authentication"
        ? "Provide a valid API key."
        : error?.kind === "network"
          ? "The list could not be loaded. Retry."
          : "The list cannot be confirmed for this identity.";
    countLine.textContent = "Not loaded.";
    showError(error);
  }
}

rowsBody.addEventListener("click", async (event) => {
  const toggle = event.target.closest("[data-expand-principal]");
  if (!toggle) return;
  const principalId = toggle.dataset.expandPrincipal;
  if (expanded.has(principalId)) {
    expanded.delete(principalId);
    renderRows();
    return;
  }
  const generation = sessionGeneration;
  try {
    // Capture the session generation before the detail request: a late
    // resolution must not mutate items, DOM, expanded, error or live region
    // once the session changed or was cleared.
    const item = await controlApi.getPrincipal(principalId);
    if (generation !== sessionGeneration) return;
    const index = currentItems.findIndex((entry) => text(entry.principal_id) === principalId);
    if (index >= 0) currentItems[index] = item;
    else currentItems = [...currentItems, item];
    expanded.add(principalId);
    renderRows();
  } catch (error) {
    if (generation !== sessionGeneration) return;
    expanded.delete(principalId);
    showError(error);
    await loadPrincipals();
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
  announce("Session set. Loading principals.");
  loadPrincipals();
});

disconnectButton.addEventListener("click", () => {
  // Invalidate any in-flight load before clearing: its late resolution must
  // not repopulate administrative data under the cleared session. Do not
  // start a replacement load: the cleared session has no credential, so a new
  // request would only produce an authentication error and clobber the
  // disconnected state the stale guard is meant to preserve.
  sessionGeneration += 1;
  credentialStore.clear();
  expanded.clear();
  currentItems = [];
  renderRows();
  hideError();
  loadingState.hidden = true;
  listWrap.hidden = true;
  listEmpty.hidden = false;
  emptyDetail.textContent = "Connect with an administrative API key to load the list.";
  countLine.textContent = "Not loaded.";
  page.dataset.state = "idle";
  announce("Session cleared.");
});

refreshButton.addEventListener("click", () => {
  loadPrincipals();
});

page.dataset.state = "idle";
