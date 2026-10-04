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
const revokeDialog = document.getElementById("revoke-dialog");
const revokeForm = document.getElementById("revoke-form");
const revokeDetail = document.getElementById("revoke-detail");
const revokeError = document.getElementById("revoke-error");
const revokeErrorTitle = document.getElementById("revoke-error-title");
const revokeErrorDetail = document.getElementById("revoke-error-detail");
const revokeSubmit = document.getElementById("revoke-submit");
const revokeCancel = document.getElementById("revoke-cancel");

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let sessionGeneration = 0;
let queryVersion = 0;
let currentFilter = null;
let currentItems = [];
let pendingRevoke = null;
let revokeInFlight = false;

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

// Revoke errors keep the 401/403 contract of the list surface: credential
// and authorization failures preserve their dedicated titles, while a
// missing grant id is reported contractually without revealing anything else.
function describeRevokeError(error) {
  if (error?.kind === "network")
    return ["API unavailable", "The control-plane API could not be reached. The grant was not revoked."];
  if (error?.kind === "authentication")
    return ["Authentication required", "Provide a valid API key. The grant was not revoked."];
  if (error?.kind === "authorization")
    return ["Access unavailable", "The grant cannot be revoked for this identity. Nothing else is revealed."];
  if (error?.kind === "not_found")
    return ["Grant not found", "The grant is no longer listed. Refresh the list; nothing was revoked."];
  if (error?.kind === "api" && error?.code === "validation_error")
    return ["Invalid grant", "The grant identifier is not a valid grant reference. Nothing was revoked."];
  return ["Request failed", error?.message ?? "Unexpected error. Nothing was revoked."];
}

function hideRevokeError() {
  revokeError.hidden = true;
  revokeErrorTitle.textContent = "Request failed";
  revokeErrorDetail.textContent = "";
}

function showRevokeError(error) {
  const [title, detail] = describeRevokeError(error);
  revokeErrorTitle.textContent = title;
  revokeErrorDetail.textContent = detail;
  revokeError.hidden = false;
  announce(`${title}. ${detail}`);
}

function closeRevokeDialog() {
  pendingRevoke = null;
  hideRevokeError();
  if (revokeDialog?.open) revokeDialog.close();
  if (!revokeInFlight && revokeSubmit) revokeSubmit.disabled = false;
  if (revokeCancel) revokeCancel.disabled = false;
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
    const grantId = text(item.grant_id);
    const row = document.createElement("tr");
    row.dataset.grantRow = grantId;
    const idCell = document.createElement("td");
    const idCode = document.createElement("code");
    idCode.className = "ma-mono";
    idCode.textContent = grantId;
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
    const revokeCell = document.createElement("td");
    const revokeButton = document.createElement("button");
    revokeButton.className = "ma-button ma-button--secondary ma-button--small";
    revokeButton.type = "button";
    revokeButton.dataset.grantRevoke = grantId;
    revokeButton.textContent = "Revoke";
    revokeButton.setAttribute("aria-label", `Revoke grant ${grantId}`);
    revokeCell.append(revokeButton);
    row.append(idCell, principalCell, actionCell, resourceCell, statusCell, revokeCell);
    rowsBody.append(row);
  }
}

function openRevokeDialog(grantId) {
  if (revokeInFlight) return;
  const known = currentItems.find((entry) => text(entry.grant_id) === grantId);
  const status = text(known?.status);
  hideRevokeError();
  if (revokeSubmit) revokeSubmit.disabled = false;
  if (revokeCancel) revokeCancel.disabled = false;
  if (status !== "" && status !== "active") {
    // CA2: an already-revoked (or otherwise inactive) grant converges
    // without a DELETE. The contractual outcome is stated, the row stays.
    pendingRevoke = null;
    revokeDetail.textContent =
      `Grant ${grantId} is already ${status}. ` +
      "The revoked lifecycle state is kept for traceability; no further action is needed.";
    if (revokeSubmit) revokeSubmit.disabled = true;
    announce(revokeDetail.textContent);
  } else {
    pendingRevoke = { grantId };
    revokeDetail.textContent =
      `Revoke grant ${grantId}? ` +
      "The grant converges to revoked and stays listed for traceability.";
  }
  revokeDialog.showModal();
}

async function loadGrants(filter) {
  const generation = sessionGeneration;
  const version = (queryVersion += 1);
  hideError();
  closeRevokeDialog();
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
    currentItems = items;
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
    currentItems = [];
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
  closeRevokeDialog();
  clearGrantRows();
  currentItems = [];
  currentFilter = null;
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
    closeRevokeDialog();
    clearGrantRows();
    currentItems = [];
    currentFilter = null;
    showInitialHint();
    page.dataset.state = "filters";
    return;
  }
  resourceFilter.value = "";
  currentFilter = { principalId: principalFilter.value };
  loadGrants(currentFilter);
});

resourceFilter.addEventListener("change", () => {
  if (!resourceFilter.value) {
    queryVersion += 1;
    hideError();
    closeRevokeDialog();
    clearGrantRows();
    currentItems = [];
    currentFilter = null;
    showInitialHint();
    page.dataset.state = "filters";
    return;
  }
  principalFilter.value = "";
  currentFilter = { resourceId: resourceFilter.value };
  loadGrants(currentFilter);
});

rowsBody.addEventListener("click", (event) => {
  const button = event.target?.closest?.("[data-grant-revoke]");
  if (!button || !rowsBody.contains(button)) return;
  const grantId = button.dataset.grantRevoke;
  if (!grantId) return;
  openRevokeDialog(grantId);
});

revokeDialog.addEventListener("cancel", (event) => {
  if (revokeInFlight) event.preventDefault();
});

revokeCancel.addEventListener("click", () => {
  if (revokeInFlight) return;
  closeRevokeDialog();
});

revokeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (revokeInFlight) return;
  if (revokeSubmit.disabled) return;
  if (!pendingRevoke) return;
  hideRevokeError();
  const generation = sessionGeneration;
  const { grantId } = pendingRevoke;
  revokeInFlight = true;
  revokeSubmit.disabled = true;
  if (revokeCancel) revokeCancel.disabled = true;
  try {
    await controlApi.revokeGrant(grantId);
    if (generation !== sessionGeneration) return;
    closeRevokeDialog();
    // CA2: revoke changes lifecycle without deleting traceability. The
    // list is refreshed in place (no harness restart) and the revoked row
    // stays rendered with its revoked badge. The outcome is announced after
    // the refresh so it remains the latest live-region message.
    const refreshed = currentFilter ? await loadGrants(currentFilter) : true;
    if (generation !== sessionGeneration) return;
    if (refreshed) announce(`Grant ${grantId} revoked. The revoked row is kept for traceability.`);  } catch (error) {
    if (generation !== sessionGeneration) return;
    showRevokeError(error);
  } finally {
    revokeInFlight = false;
    if (revokeDialog?.open) {
      if (revokeSubmit) revokeSubmit.disabled = !pendingRevoke;
      if (revokeCancel) revokeCancel.disabled = false;
    }
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
  announce("Session set. Loading filters.");
  loadFilterSources();
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  queryVersion += 1;
  credentialStore.clear();
  clearGrantRows();
  currentItems = [];
  currentFilter = null;
  hideError();
  closeRevokeDialog();
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
