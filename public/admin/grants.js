import {
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const page = document.getElementById("grants-page");
const sessionForm = document.getElementById("session-form");
const apiKeyInput = document.getElementById("api-key");
const liveRegion = document.getElementById("live-region");
const errorBox = document.getElementById("page-error");
const errorTitle = document.getElementById("page-error-title");
const errorDetail = document.getElementById("page-error-detail");
const principalFilter = document.getElementById("principal-filter");
const resourceFilter = document.getElementById("resource-filter");
const resourceNote = document.getElementById("resource-note");
const disconnectButton = document.getElementById("disconnect-button");
const loadingState = document.getElementById("list-loading");
const listWrap = document.getElementById("list-wrap");
const listEmpty = document.getElementById("list-empty");
const emptyTitle = document.getElementById("list-empty-title");
const emptyDetail = document.getElementById("list-empty-detail");
const countLine = document.getElementById("grant-count");
const rowsBody = document.getElementById("grant-rows");

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let sessionGeneration = 0;
let queryVersion = 0;

const text = (value) => (typeof value === "string" ? value : "");
const announce = (message) => {
  liveRegion.textContent = message;
};

function describeError(error) {
  if (error?.kind === "network")
    return ["API unavailable", "The control-plane API could not be reached. Check the stack and retry."];
  if (error?.kind === "authentication")
    return ["Authentication required", "Provide a valid API key. Nothing else is confirmed."];
  if (error?.kind === "authorization" || error?.kind === "not_found")
    return ["Access unavailable", "The grants cannot be confirmed for this identity. Nothing else is revealed."];
  if (error?.kind === "api" && error?.code === "validation_error")
    return ["Invalid grant filter", "Select exactly one valid Principal or Resource."];
  return ["Request failed", error?.message ?? "Unexpected error."];
}

function hideError() {
  errorBox.hidden = true;
  errorDetail.textContent = "";
}

function showError(error) {
  const [title, detail] = describeError(error);
  errorTitle.textContent = title;
  errorDetail.textContent = detail;
  errorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function resetOptions(select, placeholder) {
  select.replaceChildren();
  const option = document.createElement("option");
  option.value = "";
  option.textContent = placeholder;
  select.append(option);
  select.value = "";
}

function showInitialHint() {
  loadingState.hidden = true;
  listWrap.hidden = true;
  listEmpty.hidden = false;
  emptyTitle.textContent = "No grants to show";
  emptyDetail.textContent = "Select a Principal or Resource to load grants.";
  countLine.textContent = "Not loaded.";
}

function clearGrantRows() {
  rowsBody.replaceChildren();
}

function statusBadge(status) {
  const badge = document.createElement("span");
  badge.className = "ma-badge";
  badge.dataset.tone = status === "active" ? "success" : status === "revoked" ? "critical" : "info";
  badge.textContent = text(status) || "unknown";
  return badge;
}

function renderRows(items) {
  clearGrantRows();
  for (const item of items) {
    const row = document.createElement("tr");
    row.dataset.grantRow = text(item.grant_id);
    const idCell = document.createElement("td");
    const idCode = document.createElement("code");
    idCode.className = "ma-mono";
    idCode.textContent = text(item.grant_id);
    idCell.append(idCode);
    const principalCell = document.createElement("td");
    principalCell.className = "ma-mono";
    principalCell.textContent = text(item.principal_id);
    const actionCell = document.createElement("td");
    actionCell.textContent = text(item.action);
    const resourceCell = document.createElement("td");
    resourceCell.className = "ma-mono";
    resourceCell.textContent = `${text(item.resource?.resource_type)}/${text(item.resource?.resource_id)}`;
    const statusCell = document.createElement("td");
    statusCell.append(statusBadge(item.status));
    row.append(idCell, principalCell, actionCell, resourceCell, statusCell);
    rowsBody.append(row);
  }
}

async function loadGrants(filter) {
  const generation = sessionGeneration;
  const version = (queryVersion += 1);
  hideError();
  page.dataset.state = "loading";
  loadingState.hidden = false;
  listWrap.hidden = true;
  listEmpty.hidden = true;
  countLine.textContent = "Loading grants…";
  announce("Loading grants.");
  try {
    const payload = await controlApi.listGrants(filter);
    if (generation !== sessionGeneration || version !== queryVersion) return false;
    const items = Array.isArray(payload?.items) ? payload.items : [];
    loadingState.hidden = true;
    if (items.length === 0) {
      page.dataset.state = "empty";
      clearGrantRows();
      listEmpty.hidden = false;
      emptyTitle.textContent = "No active grant matches.";
      emptyDetail.textContent =
        "Absent grant implies deny: without an applicable active grant, the requested action is denied.";
      countLine.textContent = "No grants.";
      announce("No active grant matches. Absent grant implies deny.");
      return true;
    }
    page.dataset.state = "ready";
    renderRows(items);
    listWrap.hidden = false;
    countLine.textContent = `${items.length} grant${items.length === 1 ? "" : "s"}${payload?.truncated === true ? " (truncated)" : "."}`;
    announce(countLine.textContent);
    return true;
  } catch (error) {
    if (generation !== sessionGeneration || version !== queryVersion) return false;
    loadingState.hidden = true;
    clearGrantRows();
    showInitialHint();
    page.dataset.state = error?.kind === "network" ? "offline" : "error";
    showError(error);
    return false;
  }
}

async function loadFilterSources() {
  const generation = (sessionGeneration += 1);
  queryVersion += 1;
  hideError();
  clearGrantRows();
  showInitialHint();
  resourceNote.hidden = true;
  resourceNote.textContent = "";
  resetOptions(principalFilter, "Select a principal…");
  resetOptions(resourceFilter, "Select a resource…");
  principalFilter.disabled = true;
  resourceFilter.disabled = true;
  page.dataset.state = "loading";
  announce("Loading filter candidates.");
  const [principals, catalog] = await Promise.all([
    controlApi.listPrincipals().then(
      (payload) => ({ ok: true, payload }),
      (error) => ({ ok: false, error }),
    ),
    controlApi.listCatalogResources({ status: "active" }).then(
      (payload) => ({ ok: true, payload }),
      (error) => ({ ok: false, error }),
    ),
  ]);
  if (generation !== sessionGeneration) return;
  if (!principals.ok) {
    page.dataset.state = principals.error?.kind === "network" ? "offline" : "error";
    showError(principals.error);
    return;
  }
  for (const item of Array.isArray(principals.payload?.items) ? principals.payload.items : []) {
    const option = document.createElement("option");
    option.value = text(item.principal_id);
    if (!option.value) continue;
    option.textContent = `${text(item.display_name) || option.value} (${option.value})`;
    // Active principals are future creation candidates; every listed
    // principal stays a query filter candidate for history reads.
    if (item.status === "active") option.dataset.creationCandidate = "true";
    principalFilter.append(option);
  }
  principalFilter.disabled = false;
  if (!catalog.ok) {
    const [title] = describeError(catalog.error);
    resourceNote.textContent = `Resource catalog unavailable: ${title}. Principal queries still work.`;
    resourceNote.hidden = false;
  } else {
    for (const item of Array.isArray(catalog.payload?.items) ? catalog.payload.items : []) {
      const resourceType = text(item.resource_type);
      const resourceId = text(item.resource_id);
      if (!resourceType || !resourceId) continue;
      const option = document.createElement("option");
      option.value = resourceId;
      const displayName = text(item.discoverability?.display_name);
      option.textContent = `${displayName || resourceId} · ${resourceType}/${resourceId} · ${text(item.status)}`;
      resourceFilter.append(option);
    }
    resourceFilter.disabled = false;
  }
  page.dataset.state = "filters";
  countLine.textContent = "Not loaded.";
  announce("Filters loaded. Select a Principal or Resource to load grants.");
}

principalFilter.addEventListener("change", () => {
  if (!principalFilter.value) {
    queryVersion += 1;
    hideError();
    clearGrantRows();
    showInitialHint();
    page.dataset.state = "filters";
    return;
  }
  resourceFilter.value = "";
  loadGrants({ principalId: principalFilter.value });
});

resourceFilter.addEventListener("change", () => {
  if (!resourceFilter.value) {
    queryVersion += 1;
    hideError();
    clearGrantRows();
    showInitialHint();
    page.dataset.state = "filters";
    return;
  }
  principalFilter.value = "";
  loadGrants({ resourceId: resourceFilter.value });
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
  announce("Session set. Loading filters.");
  loadFilterSources();
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  queryVersion += 1;
  credentialStore.clear();
  clearGrantRows();
  hideError();
  resourceNote.hidden = true;
  resourceNote.textContent = "";
  resetOptions(principalFilter, "Select a principal…");
  resetOptions(resourceFilter, "Select a resource…");
  principalFilter.disabled = true;
  resourceFilter.disabled = true;
  showInitialHint();
  page.dataset.state = "idle";
  announce("Session cleared.");
});

page.dataset.state = "idle";
