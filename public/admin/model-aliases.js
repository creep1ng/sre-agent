import {
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const page = document.getElementById("model-aliases-page");
const sessionForm = document.getElementById("session-form");
const apiKeyInput = document.getElementById("api-key");
const liveRegion = document.getElementById("live-region");
const errorBox = document.getElementById("page-error");
const errorTitle = document.getElementById("page-error-title");
const loadingState = document.getElementById("list-loading");
const listWrap = document.getElementById("list-wrap");
const listEmpty = document.getElementById("list-empty");
const emptyDetail = document.getElementById("list-empty-detail");
const countLine = document.getElementById("alias-count");
const rowsBody = document.getElementById("alias-rows");
const refreshButton = document.getElementById("refresh-button");
const disconnectButton = document.getElementById("disconnect-button");
const detailSection = document.getElementById("alias-detail");
const detailSubtitle = document.getElementById("alias-detail-subtitle");
const detailLoading = document.getElementById("detail-loading");
const detailContent = document.getElementById("detail-content");
const detailErrorBox = document.getElementById("detail-error");
const detailErrorTitle = document.getElementById("detail-error-title");
const detailCloseButton = document.getElementById("detail-close-button");
const detailEditButton = document.getElementById("detail-edit-button");
const assignmentForm = document.getElementById("assignment-form");
const editConcreteModel = document.getElementById("edit-concrete-model");
const editRouter = document.getElementById("edit-router");
const editInferenceProvider = document.getElementById("edit-inference-provider");
const assignmentSaveButton = document.getElementById("assignment-save-button");
const assignmentCancelButton = document.getElementById("assignment-cancel-button");
const assignmentRefreshButton = document.getElementById("assignment-refresh-button");

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let currentItems = [];
let sessionGeneration = 0;
let detailReadVersion = 0;
let activeDetailId = null;
let activeDetailItem = null;
let pendingExpectedUpdatedAt = null;
let editMode = false;
let saveInFlight = false;
const CONCRETE_MODEL_PATTERN = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._:-]+$/;

const text = (value) => (typeof value === "string" ? value : "");
const announce = (message) => {
  liveRegion.textContent = message;
};

function describeError(error) {
  if (error?.kind === "network") return "API unavailable";
  if (error?.kind === "authentication") return "Authentication required";
  if (error?.kind === "authorization") return "Access unavailable";
  if (error?.kind === "conflict" || error?.code === "status_conflict")
    return "Alias changed; refresh and try again";
  if (error?.kind === "validation" || error?.code === "validation_error")
    return "Invalid assignment";
  if (error?.kind === "not_found") return "Alias unavailable";
  return "Request failed";
}

function hideError() {
  errorBox.hidden = true;
  errorTitle.textContent = "";
}

function showError(error) {
  const message = describeError(error);
  errorTitle.textContent = message;
  errorBox.hidden = false;
  announce(message);
}

function monoCell(value) {
  const cell = document.createElement("td");
  cell.className = "ma-mono";
  cell.textContent = value || "—";
  return cell;
}

function statusCell(status) {
  const cell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "ma-badge";
  badge.dataset.tone = status === "active" ? "success" : status === "inactive" ? "warning" : "info";
  badge.textContent = text(status) || "unknown";
  cell.append(badge);
  return cell;
}

function renderRows() {
  rowsBody.replaceChildren();
  for (const item of currentItems) {
    const aliasId = text(item.model_alias_id) || text(item.alias);
    const row = document.createElement("tr");
    row.dataset.aliasRow = aliasId;
    row.append(
      monoCell(text(item.alias)),
      monoCell(text(item.concrete_model)),
      monoCell(text(item.router)),
      monoCell(text(item.inference_provider)),
      statusCell(item.status),
      monoCell(text(item.updated_at)),
      detailCell(aliasId),
    );
    rowsBody.append(row);
  }
}

function detailCell(aliasId) {
  const cell = document.createElement("td");
  const action = document.createElement("button");
  action.type = "button";
  action.className = "ma-button ma-button--secondary ma-button--small";
  action.dataset.detailOpen = aliasId;
  action.textContent = "Details";
  action.setAttribute("aria-label", `Open details for ${aliasId}`);
  cell.append(action);
  return cell;
}

function hideDetailError() {
  detailErrorBox.hidden = true;
  detailErrorTitle.textContent = "";
}

function showDetailError(error) {
  const message = describeError(error);
  detailErrorTitle.textContent = message;
  detailErrorBox.hidden = false;
  announce(message);
}

function exitEditMode() {
  editMode = false;
  pendingExpectedUpdatedAt = activeDetailItem ? text(activeDetailItem.updated_at) || null : null;
  assignmentForm.hidden = true;
  editConcreteModel.removeAttribute("aria-invalid");
  editRouter.removeAttribute("aria-invalid");
  editInferenceProvider.removeAttribute("aria-invalid");
  assignmentRefreshButton.hidden = true;
  if (activeDetailItem) detailEditButton.hidden = false;
}

function enterEditMode() {
  if (!activeDetailItem) return;
  editMode = true;
  pendingExpectedUpdatedAt = text(activeDetailItem.updated_at) || null;
  editConcreteModel.value = text(activeDetailItem.concrete_model);
  editRouter.value = text(activeDetailItem.router);
  editInferenceProvider.value = text(activeDetailItem.inference_provider);
  editConcreteModel.removeAttribute("aria-invalid");
  editRouter.removeAttribute("aria-invalid");
  editInferenceProvider.removeAttribute("aria-invalid");
  hideDetailError();
  assignmentRefreshButton.hidden = true;
  assignmentForm.hidden = false;
  detailEditButton.hidden = true;
  editConcreteModel.focus();
}

function closeDetailState() {
  activeDetailId = null;
  activeDetailItem = null;
  pendingExpectedUpdatedAt = null;
  editMode = false;
  saveInFlight = false;
  detailSection.hidden = true;
  detailLoading.hidden = true;
  detailContent.hidden = true;
  detailContent.replaceChildren();
  assignmentForm.hidden = true;
  detailEditButton.hidden = true;
  assignmentRefreshButton.hidden = true;
  hideDetailError();
  detailSubtitle.textContent = "No alias selected.";
}

function closeDetail() {
  detailReadVersion += 1;
  closeDetailState();
}

function detailFields(item) {
  return [
    ["model_alias_id", item.model_alias_id],
    ["alias", item.alias],
    ["concrete_model", item.concrete_model],
    ["router", item.router],
    ["inference_provider", item.inference_provider],
    ["status", item.status],
    ["updated_at", item.updated_at],
  ];
}

function renderDetail(item) {
  detailContent.replaceChildren();
  for (const [name, value] of detailFields(item)) {
    const term = document.createElement("dt");
    term.textContent = name;
    const def = document.createElement("dd");
    def.className = "ma-mono";
    def.dataset.detailField = name;
    def.textContent = text(value) || "—";
    detailContent.append(term, def);
  }
  detailContent.hidden = false;
}

function applyAuthoritativeDetail(item) {
  activeDetailItem = item;
  pendingExpectedUpdatedAt = text(item.updated_at) || null;
  renderDetail(item);
  detailEditButton.hidden = false;
  if (editMode) {
    editConcreteModel.value = text(item.concrete_model);
    editRouter.value = text(item.router);
    editInferenceProvider.value = text(item.inference_provider);
  } else {
    assignmentForm.hidden = true;
  }
  const aliasId = text(item.model_alias_id) || text(item.alias);
  const index = currentItems.findIndex(
    (entry) => (text(entry.model_alias_id) || text(entry.alias)) === aliasId,
  );
  if (index >= 0) {
    currentItems[index] = item;
    renderRows();
  }
}

function buildAssignmentBody() {
  const concreteModel = editConcreteModel.value.trim();
  const router = editRouter.value.trim();
  const inferenceProvider = editInferenceProvider.value.trim();
  editConcreteModel.setAttribute("aria-invalid", String(concreteModel === ""));
  editRouter.setAttribute("aria-invalid", String(router === ""));
  editInferenceProvider.setAttribute("aria-invalid", String(inferenceProvider === ""));
  if (concreteModel === "" || router === "" || inferenceProvider === "") return null;
  if (router !== "openrouter") {
    editRouter.setAttribute("aria-invalid", "true");
    return null;
  }
  if (!CONCRETE_MODEL_PATTERN.test(concreteModel)) {
    editConcreteModel.setAttribute("aria-invalid", "true");
    return null;
  }
  if (typeof pendingExpectedUpdatedAt !== "string" || pendingExpectedUpdatedAt === "") return null;
  return {
    concrete_model: concreteModel,
    router,
    inference_provider: inferenceProvider,
    expected_updated_at: pendingExpectedUpdatedAt,
  };
}

async function refreshDetail(aliasId, generation, readVersion) {
  try {
    const item = await controlApi.getModelAlias(aliasId);
    if (generation !== sessionGeneration || readVersion !== detailReadVersion) return;
    applyAuthoritativeDetail(item);
    detailLoading.hidden = true;
    detailSubtitle.textContent = `${text(item.alias) || aliasId} · authoritative detail.`;
  } catch (error) {
    if (generation !== sessionGeneration || readVersion !== detailReadVersion) return;
    detailLoading.hidden = true;
    detailContent.hidden = true;
    detailContent.replaceChildren();
    detailSubtitle.textContent = "Detail unavailable.";
    showDetailError(error);
  }
}

async function openDetail(aliasId) {
  const generation = sessionGeneration;
  const readVersion = detailReadVersion + 1;
  detailReadVersion = readVersion;
  activeDetailId = aliasId;
  activeDetailItem = null;
  pendingExpectedUpdatedAt = null;
  editMode = false;
  assignmentForm.hidden = true;
  detailEditButton.hidden = true;
  assignmentRefreshButton.hidden = true;
  hideDetailError();
  detailSection.hidden = false;
  detailContent.hidden = true;
  detailContent.replaceChildren();
  detailLoading.hidden = false;
  detailSubtitle.textContent = `Loading ${aliasId}…`;
  try {
    const item = await controlApi.getModelAlias(aliasId);
    if (generation !== sessionGeneration || readVersion !== detailReadVersion) return false;
    applyAuthoritativeDetail(item);
    detailLoading.hidden = true;
    detailSubtitle.textContent = `${text(item.alias) || aliasId} · authoritative detail.`;
    announce(`Detail loaded for ${aliasId}.`);
    return true;
  } catch (error) {
    if (generation !== sessionGeneration || readVersion !== detailReadVersion) return false;
    detailLoading.hidden = true;
    detailContent.hidden = true;
    detailContent.replaceChildren();
    detailSubtitle.textContent = "Detail unavailable.";
    showDetailError(error);
    return false;
  }
}

async function loadAliases() {
  const generation = sessionGeneration + 1;
  sessionGeneration = generation;
  hideError();
  page.dataset.state = "loading";
  loadingState.hidden = false;
  listWrap.hidden = true;
  listEmpty.hidden = true;
  countLine.textContent = "Loading aliases…";
  announce("Loading aliases.");
  try {
    const payload = await controlApi.listModelAliases();
    if (generation !== sessionGeneration) return false;
    currentItems = Array.isArray(payload?.items) ? payload.items : [];
    renderRows();
    loadingState.hidden = true;
    if (currentItems.length === 0) {
      page.dataset.state = "empty";
      listEmpty.hidden = false;
      emptyDetail.textContent = "The API returned an empty aliases list.";
      countLine.textContent = "No aliases.";
      announce("No aliases.");
      return true;
    }
    page.dataset.state = "ready";
    listWrap.hidden = false;
    countLine.textContent = `${currentItems.length} alias${currentItems.length === 1 ? "" : "es"}${payload?.truncated === true ? " (truncated)" : "."}`;
    announce(countLine.textContent);
    return true;
  } catch (error) {
    if (generation !== sessionGeneration) return false;
    currentItems = [];
    renderRows();
    activeDetailId = null;
    closeDetailState();
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

sessionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = apiKeyInput.value.trim();
  if (!value) {
    errorTitle.textContent = "Enter an API key.";
    errorBox.hidden = false;
    announce("Enter an API key.");
    return;
  }
  credentialStore.set(value);
  apiKeyInput.value = "";
  announce("Session set. Loading aliases.");
  loadAliases();
});

disconnectButton.addEventListener("click", () => {
  sessionGeneration += 1;
  detailReadVersion += 1;
  activeDetailId = null;
  closeDetailState();
  credentialStore.clear();
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
  loadAliases();
});

rowsBody.addEventListener("click", (event) => {
  const action = event.target.closest("[data-detail-open]");
  if (!action) return;
  openDetail(action.dataset.detailOpen);
});

detailCloseButton.addEventListener("click", () => {
  closeDetail();
});

detailEditButton.addEventListener("click", () => {
  enterEditMode();
});

assignmentCancelButton.addEventListener("click", () => {
  exitEditMode();
  hideDetailError();
});

assignmentRefreshButton.addEventListener("click", () => {
  const aliasId = activeDetailId;
  if (!aliasId) return;
  hideDetailError();
  assignmentRefreshButton.hidden = true;
  refreshDetail(aliasId, sessionGeneration, detailReadVersion);
});

assignmentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (saveInFlight || !activeDetailId) return;
  hideDetailError();
  const body = buildAssignmentBody();
  if (!body) {
    showDetailError({ kind: "validation", code: "validation_error" });
    return;
  }
  const generation = sessionGeneration;
  const readVersion = detailReadVersion;
  const aliasId = activeDetailId;
  saveInFlight = true;
  assignmentSaveButton.disabled = true;
  try {
    const updated = await controlApi.replaceModelAliasAssignment(aliasId, body);
    if (generation !== sessionGeneration || readVersion !== detailReadVersion) return;
    exitEditMode();
    applyAuthoritativeDetail(updated);
    detailSubtitle.textContent = `${text(updated.alias) || aliasId} · authoritative detail.`;
    announce(`Assignment updated for ${aliasId}.`);
  } catch (error) {
    if (generation !== sessionGeneration || readVersion !== detailReadVersion) return;
    showDetailError(error);
    if (error?.kind === "conflict" || error?.code === "status_conflict") {
      assignmentRefreshButton.hidden = false;
    }
  } finally {
    saveInFlight = false;
    assignmentSaveButton.disabled = false;
  }
});

page.dataset.state = "idle";
