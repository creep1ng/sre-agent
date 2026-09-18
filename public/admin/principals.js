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
const createButton = document.getElementById("create-button");
const createDialog = document.getElementById("create-dialog");
const createForm = document.getElementById("create-form");
const createPrincipalId = document.getElementById("create-principal-id");
const createDisplayName = document.getElementById("create-display-name");
const createKind = document.getElementById("create-kind");
const createSubmit = document.getElementById("create-submit");
const createCancel = document.getElementById("create-cancel");
const createErrorBox = document.getElementById("create-error");
const createErrorTitle = document.getElementById("create-error-title");
const createErrorDetail = document.getElementById("create-error-detail");
const deactivateDialog = document.getElementById("deactivate-dialog");
const deactivateForm = document.getElementById("deactivate-form");
const deactivateTitle = document.getElementById("deactivate-title");
const deactivateDetail = document.getElementById("deactivate-detail");
const deactivateSubmit = document.getElementById("deactivate-submit");
const deactivateCancel = document.getElementById("deactivate-cancel");
const deactivateErrorBox = document.getElementById("deactivate-error");
const deactivateErrorTitle = document.getElementById("deactivate-error-title");
const deactivateErrorDetail = document.getElementById("deactivate-error-detail");
const issueDialog = document.getElementById("issue-dialog");
const issueForm = document.getElementById("issue-form");
const issueExpiresAt = document.getElementById("issue-expires-at");
const issueSubmit = document.getElementById("issue-submit");
const issueCancel = document.getElementById("issue-cancel");
const issueErrorBox = document.getElementById("issue-error");
const issueErrorTitle = document.getElementById("issue-error-title");
const issueErrorDetail = document.getElementById("issue-error-detail");
const secretDialog = document.getElementById("secret-dialog");
const secretValue = document.getElementById("secret-value");
const secretClose = document.getElementById("secret-close");

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
const expanded = new Set();
let currentItems = [];
// Per-principal read version: every authoritative write of one Principal
// bumps its version, and a detail GET resolving with an older version never
// writes. A status mutation is not a session change, so sessionGeneration
// alone cannot invalidate it.
const principalVersions = new Map();
const principalVersionOf = (principalId) => principalVersions.get(principalId) ?? 0;
const touchPrincipalVersion = (principalId) =>
  principalVersions.set(principalId, principalVersionOf(principalId) + 1);
// Monotonic load generation: every loadPrincipals() call owns the UI until a
// newer load starts or the session is cleared. A late resolution from a
// previous generation (e.g. fetched with an older credential) must never
// render.
let sessionGeneration = 0;
const PRINCIPAL_ID_RE = /^[a-z][a-z0-9_-]{2,63}$/;
// Idempotency-Key (B1): `principal-create-` + 16 getRandomValues bytes as hex
// (49 chars, 16..128, 128-bit). Reused only for the exact same payload; any
// principal_id/kind/display_name change mints a fresh key (backend binds key).
function newIdempotencyKey() {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return `principal-create-${[...b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}
function createBodyKey(body) {
  return `${body.principal_id}\n${body.kind}\n${body.display_name}`;
}
let pendingIdempotencyKey = null;
let pendingCreateBodyKey = null;
// Real-request lock (B1): independent of dialog state. Set while POST +
// authoritative refresh settle; never cleared by open/cancel/disconnect.
let createInFlight = false;
// Real-request lock (B2): PUT status settle; never cleared by UI.
let statusInFlight = false;
let pendingDeactivate = null;
let credentialIssueInFlight = false;
let pendingIssue = null;
let pendingSecret = null;
const credentialCache = new Map();
// Read version per Principal for its credential collection: every new
// listCredentials read invalidates older ones, so only the latest read
// may write the cache. Separate from B2 principalVersions, which guards
// the Principal object itself.
const credentialReadVersions = new Map();
const credentialReadVersionOf = (principalId) => credentialReadVersions.get(principalId) ?? 0;
const touchCredentialReadVersion = (principalId) => {
  const next = credentialReadVersionOf(principalId) + 1;
  credentialReadVersions.set(principalId, next);
  return next;
};

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

function hideCreateError() {
  createErrorBox.hidden = true;
  createErrorTitle.textContent = "";
  createErrorDetail.textContent = "";
}

function describeCreateError(error) {
  // CREATE-only: shared 401/403/409/network copy + POST api codes. not_found untouched (B2).
  if (error?.kind === "validation")
    return ["Invalid principal", error?.message ?? "Check the highlighted fields. Nothing was created."];
  if (error?.kind === "api" && error?.code === "validation_error")
    return ["Invalid principal", "Check the highlighted fields. Nothing was created."];
  if (error?.kind === "api" && error?.code === "invalid_idempotency_key")
    return ["Request failed", "The retry token was rejected. Refresh and retry; nothing was overwritten."];
  if (error?.kind === "api" && error?.code === "audit_unavailable")
    return ["Service unavailable", "The request was not completed. Refresh and retry."];
  if (error?.kind === "api" || error?.kind === "invalid_response")
    return ["Request failed", error?.message ?? "Unexpected error. Nothing was created."];
  return describeError(error);
}

function showCreateError(error) {
  const [title, detail] = describeCreateError(error);
  createErrorTitle.textContent = title;
  createErrorDetail.textContent = detail;
  createErrorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function hideDeactivateError() {
  deactivateErrorBox.hidden = true;
  deactivateErrorTitle.textContent = "";
  deactivateErrorDetail.textContent = "";
}

function describeStatusError(error) {
  if (error?.kind === "api" && error?.code === "validation_error")
    return ["Invalid status change", "Check the principal state. Nothing was changed."];
  if (error?.kind === "api" && error?.code === "audit_unavailable")
    return ["Service unavailable", "The request was not completed. Refresh and retry."];
  if (error?.kind === "api" || error?.kind === "invalid_response")
    return ["Request failed", error?.message ?? "Unexpected error. Nothing was changed."];
  return describeError(error);
}

function showDeactivateError(error) {
  const [title, detail] = describeStatusError(error);
  deactivateErrorTitle.textContent = title;
  deactivateErrorDetail.textContent = detail;
  deactivateErrorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function hideIssueError() {
  issueErrorBox.hidden = true;
  issueErrorTitle.textContent = "";
  issueErrorDetail.textContent = "";
}

function describeCredentialError(error) {
  if (error?.kind === "conflict")
    return ["Request conflict", "The retry token was already used with different data. Start a new issuance."];
  if (error?.kind === "replay")
    return ["Secret unavailable", error?.message ?? "The secret cannot be shown again."];
  if (error?.kind === "api" && error?.code === "validation_error")
    return ["Invalid credential request", "Check the expiry value. Nothing was issued."];
  if (error?.kind === "api" || error?.kind === "invalid_response")
    return ["Request failed", error?.message ?? "Unexpected error. Nothing was issued."];
  return describeError(error);
}

function showIssueError(error) {
  const [title, detail] = describeCredentialError(error);
  issueErrorTitle.textContent = title;
  issueErrorDetail.textContent = detail;
  issueErrorBox.hidden = false;
  announce(`${title}. ${detail}`);
}

function validateCreateFields() {
  const principalId = createPrincipalId.value.trim();
  const displayName = createDisplayName.value.trim();
  const kind = createKind.value;
  const problems = [];
  const idOk = PRINCIPAL_ID_RE.test(principalId);
  const nameOk = displayName.length >= 1 && displayName.length <= 200;
  const kindOk = kind === "human" || kind === "agent";
  createPrincipalId.setAttribute("aria-invalid", String(!idOk));
  createDisplayName.setAttribute("aria-invalid", String(!nameOk));
  createKind.setAttribute("aria-invalid", String(!kindOk));
  if (!idOk) problems.push("principal ID");
  if (!nameOk) problems.push("display name");
  if (!kindOk) problems.push("kind");
  if (problems.length > 0) {
    return {
      ok: false,
      error: {
        kind: "validation",
        message: `Check the highlighted fields (${problems.join(", ")}). Nothing was created.`,
      },
    };
  }
  return { ok: true, body: { principal_id: principalId, kind, display_name: displayName } };
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
  if (item.status === "active") {
    const deactivate = document.createElement("button");
    deactivate.className = "ma-button ma-button--secondary ma-button--small";
    deactivate.type = "button";
    deactivate.dataset.deactivatePrincipal = principalId;
    deactivate.textContent = "Deactivate";
    panel.append(deactivate);
  } else {
    const noAction = document.createElement("p");
    noAction.className = "ma-panel__description";
    noAction.dataset.deactivateUnavailable = principalId;
    noAction.textContent = "No actions available.";
    panel.append(noAction);
  }
  const issue = document.createElement("button");
  issue.className = "ma-button ma-button--secondary ma-button--small";
  issue.type = "button";
  issue.dataset.issueCredential = principalId;
  issue.textContent = "Issue credential";
  panel.append(issue);
  const cached = credentialCache.get(principalId);
  if (cached && !cached.error && cached.items.length > 0) {
    const credList = document.createElement("ul");
    credList.dataset.credentialList = principalId;
    for (const cred of cached.items) {
      const row = document.createElement("li");
      const code = document.createElement("code");
      code.className = "ma-mono";
      const span = typeof cred.expires_at === "string" ? ` → ${cred.expires_at}` : "";
      code.textContent = `${text(cred.prefix)} … ${text(cred.credential_id)} · ${text(cred.status)} · ${text(cred.created_at)}${span}`;
      row.append(code);
      credList.append(row);
    }
    panel.append(credList);
  } else {
    const note = document.createElement("p");
    note.className = "ma-panel__description";
    if (!cached) {
      note.textContent = "Loading credentials…";
    } else if (cached.error) {
      const [title, detailText] = describeError(cached.error);
      note.textContent = `${title}. ${detailText}`;
      note.dataset.credentialsError = principalId;
      note.dataset.errorKind = cached.error.kind ?? "unknown";
    } else {
      note.textContent = "No credentials.";
      note.dataset.credentialsEmpty = principalId;
    }
    panel.append(note);
  }
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

async function loadCredentials(principalId) {
  const generation = sessionGeneration;
  const readVersion = touchCredentialReadVersion(principalId);
  try {
    const payload = await controlApi.listCredentials(principalId);
    if (generation !== sessionGeneration) return false;
    if (readVersion !== credentialReadVersionOf(principalId)) return false;
    credentialCache.set(principalId, {
      items: Array.isArray(payload?.items) ? payload.items : [],
      error: null,
      loading: false,
    });
    if (expanded.has(principalId)) renderRows();
    return true;
  } catch (error) {
    if (generation !== sessionGeneration) return false;
    if (readVersion !== credentialReadVersionOf(principalId)) return false;
    credentialCache.set(principalId, { items: [], error, loading: false });
    if (expanded.has(principalId)) renderRows();
    return false;
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
    if (generation !== sessionGeneration) return false;
    currentItems = Array.isArray(payload?.items) ? payload.items : [];
    renderRows();
    loadingState.hidden = true;
    if (currentItems.length === 0) {
      page.dataset.state = "empty";
      listEmpty.hidden = false;
      emptyDetail.textContent = "The API returned an empty principals list.";
      countLine.textContent = "No principals.";
      announce("No principals.");
      expanded.clear();
      credentialCache.clear();
      credentialReadVersions.clear();
      return true;
    }
    page.dataset.state = "ready";
    listWrap.hidden = false;
    countLine.textContent = `${currentItems.length} principal${currentItems.length === 1 ? "" : "s"}${payload?.truncated === true ? " (truncated)" : "."}`;
    announce(countLine.textContent);
    // A refresh orphans pending credential reads (stale generation) without
    // replacing them: re-request credentials for still-expanded principals
    // that still exist, and drop vanished ones entirely.
    const currentIds = new Set(currentItems.map((item) => text(item.principal_id)));
    for (const principalId of [...expanded]) {
      if (!currentIds.has(principalId)) {
        expanded.delete(principalId);
        credentialCache.delete(principalId);
        credentialReadVersions.delete(principalId);
        continue;
      }
      loadCredentials(principalId);
    }
    return true;
  } catch (error) {
    if (generation !== sessionGeneration) return false;
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
    return false;
  }
}

function openDeactivateDialog(principalId) {
  const item = currentItems.find((entry) => text(entry.principal_id) === principalId);
  if (!item || item.status !== "active" || typeof item.updated_at !== "string") return;
  hideDeactivateError();
  pendingDeactivate = { principalId, expected_updated_at: item.updated_at };
  deactivateTitle.textContent = `Deactivate ${principalId}?`;
  deactivateDetail.textContent = `Principal ${principalId} is active.`;
  if (!statusInFlight) {
    deactivateSubmit.disabled = false;
    if (deactivateCancel) deactivateCancel.disabled = false;
  }
  if (!deactivateDialog.open) {
    if (typeof deactivateDialog.showModal === "function") deactivateDialog.showModal();
    else deactivateDialog.setAttribute("open", "");
  }
  deactivateSubmit.focus();
}

function newCredentialKey() {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return `credential-issue-${[...b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
}

function openIssueDialog(principalId) {
  if (!currentItems.some((entry) => text(entry.principal_id) === principalId)) return;
  hideIssueError();
  issueDialog.dataset.principalId = principalId;
  if (!issueDialog.open) {
    if (typeof issueDialog.showModal === "function") issueDialog.showModal();
    else issueDialog.setAttribute("open", "");
  }
  issueSubmit.focus();
}

rowsBody.addEventListener("click", async (event) => {
  const issue = event.target.closest("[data-issue-credential]");
  if (issue) {
    openIssueDialog(issue.dataset.issueCredential);
    return;
  }
  const deactivate = event.target.closest("[data-deactivate-principal]");
  if (deactivate) {
    openDeactivateDialog(deactivate.dataset.deactivatePrincipal);
    return;
  }
  const toggle = event.target.closest("[data-expand-principal]");
  if (!toggle) return;
  const principalId = toggle.dataset.expandPrincipal;
  if (expanded.has(principalId)) {
    expanded.delete(principalId);
    renderRows();
    return;
  }
  const generation = sessionGeneration;
  const itemVersion = principalVersionOf(principalId);
  try {
    // Capture the session generation before the detail request: a late
    // resolution must not mutate items, DOM, expanded, error or live region
    // once the session changed or was cleared.
    const item = await controlApi.getPrincipal(principalId);
    if (generation !== sessionGeneration) return;
    if (itemVersion !== principalVersionOf(principalId)) return;
    const index = currentItems.findIndex((entry) => text(entry.principal_id) === principalId);
    if (index >= 0) currentItems[index] = item;
    else currentItems = [...currentItems, item];
    touchPrincipalVersion(principalId);
    expanded.add(principalId);
    renderRows();
    loadCredentials(principalId);
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
  principalVersions.clear();
  renderRows();
  hideError();
  // Clear may close the UI and invalidate the generation, but it never
  // clears the in-flight request state: a late POST must stay stale-blocked
  // and must not enable a concurrent second create.
  if (!createInFlight) {
    pendingIdempotencyKey = null;
    pendingCreateBodyKey = null;
  }
  if (createDialog?.open) createDialog.close();
  hideCreateError();
  if (!createInFlight) {
    if (createSubmit) createSubmit.disabled = false;
    if (createCancel) createCancel.disabled = false;
  }
  if (deactivateDialog?.open) deactivateDialog.close();
  hideDeactivateError();
  if (!statusInFlight) {
    pendingDeactivate = null;
    if (deactivateSubmit) deactivateSubmit.disabled = false;
    if (deactivateCancel) deactivateCancel.disabled = false;
  }
  if (issueDialog?.open) issueDialog.close();
  // The holder is always discarded: an in-flight request already captured
  // its key/body in locals, so a later session can never reuse this key.
  pendingIssue = null;
  if (!credentialIssueInFlight) {
    issueSubmit.disabled = false;
    issueCancel.disabled = false;
  }
  if (secretDialog?.open) secretDialog.close();
  wipeSecret();
  credentialCache.clear();
  credentialReadVersions.clear();
  loadingState.hidden = true;
  listWrap.hidden = true;
  listEmpty.hidden = false;
  emptyDetail.textContent = "Connect with an administrative API key to load the list.";
  countLine.textContent = "Not loaded.";
  page.dataset.state = "idle";
  announce("Session cleared.");
});

deactivateDialog.addEventListener("cancel", (event) => {
  if (statusInFlight) event.preventDefault();
});

deactivateCancel.addEventListener("click", () => {
  if (statusInFlight) return;
  deactivateDialog.close();
});

deactivateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (statusInFlight) return;
  if (deactivateSubmit.disabled) return;
  if (!pendingDeactivate) return;
  hideDeactivateError();
  // expected_updated_at from dialog open (authoritative); no second PUT.
  const generation = sessionGeneration;
  const { principalId, expected_updated_at } = pendingDeactivate;
  statusInFlight = true;
  deactivateSubmit.disabled = true;
  if (deactivateCancel) deactivateCancel.disabled = true;
  let allowRetry = true;
  try {
    const updated = await controlApi.replacePrincipalStatus(principalId, {
      status: "inactive",
      expected_updated_at,
    });
    if (generation !== sessionGeneration) return;
    const index = currentItems.findIndex((entry) => text(entry.principal_id) === principalId);
    if (index >= 0) currentItems[index] = updated;
    else currentItems = [...currentItems, updated];
    touchPrincipalVersion(principalId);
    pendingDeactivate = null;
    deactivateDialog.close();
    renderRows();
    announce(`Principal ${principalId} deactivated.`);
  } catch (error) {
    if (generation !== sessionGeneration) return;
    const isConflict =
      error?.kind === "conflict" || (error?.kind === "api" && error?.code === "status_conflict");
    showDeactivateError(error);
    if (isConflict) {
      allowRetry = false;
      try {
        const fresh = await controlApi.getPrincipal(principalId);
        if (generation !== sessionGeneration) return;
        const index = currentItems.findIndex((entry) => text(entry.principal_id) === principalId);
        if (index >= 0) currentItems[index] = fresh;
        else currentItems = [...currentItems, fresh];
        touchPrincipalVersion(principalId);
        if (fresh?.status === "active" && typeof fresh?.updated_at === "string") {
          pendingDeactivate = { principalId, expected_updated_at: fresh.updated_at };
          allowRetry = true;
          renderRows();
          showDeactivateError(error);
        } else if (fresh?.status !== "active") {
          pendingDeactivate = null;
          deactivateDialog.close();
          renderRows();
          announce(`Principal ${principalId} is now inactive.`);
        } else {
          pendingDeactivate = null;
          showDeactivateError({
            kind: "invalid_response",
            message: "The principal refresh was unusable. Collapse and expand to retry.",
          });
        }
      } catch (refreshError) {
        if (generation !== sessionGeneration) return;
        pendingDeactivate = null;
        showDeactivateError(refreshError);
      }
    }
  } finally {
    statusInFlight = false;
    if (allowRetry && deactivateSubmit) deactivateSubmit.disabled = false;
    if (deactivateCancel) deactivateCancel.disabled = false;
  }
});

function wipeSecret() {
  pendingSecret = null;
  secretValue.textContent = "";
}

issueDialog.addEventListener("cancel", (event) => {
  if (credentialIssueInFlight) event.preventDefault();
});

issueCancel.addEventListener("click", () => {
  if (credentialIssueInFlight) return;
  pendingIssue = null;
  issueDialog.close();
});

secretClose.addEventListener("click", () => {
  wipeSecret();
  secretDialog.close();
});

secretDialog.addEventListener("cancel", () => {
  wipeSecret();
});

issueForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (credentialIssueInFlight) return;
  const principalId = issueDialog.dataset.principalId;
  if (!principalId) return;
  hideIssueError();
  const generation = sessionGeneration;
  const rawExpiry = issueExpiresAt.value.trim();
  const body = rawExpiry === "" ? {} : { expires_at: rawExpiry };
  const bodyKey = `${principalId}\n${JSON.stringify(body)}`;
  if (pendingIssue === null || pendingIssue.principalId !== principalId || pendingIssue.bodyKey !== bodyKey) {
    pendingIssue = { principalId, body, bodyKey, idempotencyKey: newCredentialKey() };
  }
  credentialIssueInFlight = true;
  issueSubmit.disabled = true;
  issueCancel.disabled = true;
  // The real mutation goes out now: any list read started before this POST
  // must not overwrite the authoritative refresh that follows it.
  touchCredentialReadVersion(principalId);
  try {
    const issued = await controlApi.issueCredential(principalId, body, pendingIssue.idempotencyKey);
    if (generation !== sessionGeneration) return;
    pendingIssue = null;
    if (issued?.secret_revealed === true && typeof issued?.key === "string") {
      pendingSecret = issued.key;
      secretValue.textContent = issued.key;
      issueDialog.close();
      if (typeof secretDialog.showModal === "function") secretDialog.showModal();
      else secretDialog.setAttribute("open", "");
      announce("Credential issued. Copy the secret now. It will not be shown again.");
    } else {
      showIssueError({
        kind: "replay",
        message: "Credential exists, but its secret is no longer available. Rotate or revoke it before use.",
      });
    }
    await loadCredentials(principalId);
  } catch (error) {
    if (generation !== sessionGeneration) return;
    showIssueError(error);
    // Reconcile: the pre-POST touch invalidated the previous list read, so
    // refresh authoritatively instead of stranding "Loading credentials…".
    // This starts the newest read version, keeps the retry key, no success.
    await loadCredentials(principalId);
  } finally {
    credentialIssueInFlight = false;
    issueSubmit.disabled = false;
    issueCancel.disabled = false;
  }
});

refreshButton.addEventListener("click", () => {
  loadPrincipals();
});

createButton.addEventListener("click", () => {
  hideCreateError();
  createPrincipalId.removeAttribute("aria-invalid");
  createDisplayName.removeAttribute("aria-invalid");
  createKind.removeAttribute("aria-invalid");
  // New attempt: drop retry token; fresh key minted on submit for that payload.
  // Never reset while a real POST is in flight: reopen must stay locked.
  if (!createInFlight) {
    pendingIdempotencyKey = null;
    pendingCreateBodyKey = null;
    createSubmit.disabled = false;
    if (createCancel) createCancel.disabled = false;
  }
  if (!createDialog.open) {
    if (typeof createDialog.showModal === "function") createDialog.showModal();
    else createDialog.setAttribute("open", "");
  }
  createPrincipalId.focus();
});

createDialog.addEventListener("cancel", (event) => {
  if (createInFlight) event.preventDefault();
});

createCancel.addEventListener("click", () => {
  if (createInFlight) return;
  createDialog.close();
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (createInFlight) return;
  if (createSubmit.disabled) return;
  hideCreateError();
  const checked = validateCreateFields();
  if (!checked.ok) {
    showCreateError(checked.error);
    return;
  }
  // Stale guard: late resolution must not touch UI once session changed/cleared.
  const generation = sessionGeneration;
  const bodyKey = createBodyKey(checked.body);
  if (pendingIdempotencyKey === null || pendingCreateBodyKey !== bodyKey) {
    pendingIdempotencyKey = newIdempotencyKey();
    pendingCreateBodyKey = bodyKey;
  }
  const idempotencyKey = pendingIdempotencyKey;
  createInFlight = true;
  createSubmit.disabled = true;
  if (createCancel) createCancel.disabled = true;
  try {
    // Real POST only; no optimistic insert. Body uses contract names verbatim.
    const created = await controlApi.createPrincipal(checked.body, idempotencyKey);
    if (generation !== sessionGeneration) return;
    const createdId = text(created?.principal_id) || checked.body.principal_id;
    createDialog.close();
    createForm.reset();
    pendingIdempotencyKey = null;
    pendingCreateBodyKey = null;
    // POST alone never authorizes UI success. Only the authoritative refresh
    // does: announce only when it succeeded and still owns the UI.
    // Never insert POST payload directly.
    const refreshed = await loadPrincipals();
    if (refreshed === true && sessionGeneration === generation + 1) {
      const countText = countLine.textContent === "Not loaded." ? "" : ` ${countLine.textContent}`;
      announce(`Principal ${createdId} created.${countText}`);
    }
  } catch (error) {
    if (generation !== sessionGeneration) return;
    // Keep form data; same token only for the same exact payload.
    showCreateError(error);
  } finally {
    // Request-scoped lock: always released, even after stale/disconnect, so
    // buttons never stay permanently disabled. Stale guard above already
    // prevented any authoritative UI write.
    createInFlight = false;
    if (createSubmit) createSubmit.disabled = false;
    if (createCancel) createCancel.disabled = false;
  }
});

page.dataset.state = "idle";
