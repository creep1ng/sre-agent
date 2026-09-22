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

const credentialStore = createMemoryCredentialStore();
const controlApi = createAdministrativeApiClient({ credentialStore });
let currentItems = [];
let sessionGeneration = 0;

const text = (value) => (typeof value === "string" ? value : "");
const announce = (message) => {
  liveRegion.textContent = message;
};

function describeError(error) {
  if (error?.kind === "network") return "API unavailable";
  if (error?.kind === "authentication") return "Authentication required";
  if (error?.kind === "authorization") return "Access unavailable";
  if (error?.kind === "validation" || error?.code === "validation_error")
    return "Invalid request";
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
    );
    rowsBody.append(row);
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

page.dataset.state = "idle";
