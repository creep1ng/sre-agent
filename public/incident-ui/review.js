import {
  ApiClientError,
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

// Acciones de revisión/mitigación del workflow 1.0.0, derivadas de
// mitigation_approval y run-command.schema.yaml. Versión o estado
// desconocidos no ofrecen nada. El envío llega en el slice 41a-2.
const REVIEW_ACTIONS = Object.freeze({
  "1.0.0": Object.freeze({
    mitigating: Object.freeze([
      { command: "approve_mitigation", transition: "apply_mitigation", outcome: "approve", label: "Aprobar mitigación" },
      { command: "reject_mitigation", transition: "reject_mitigation", outcome: "reject", label: "Rechazar mitigación" },
      { command: "request_changes", transition: "reject_mitigation", outcome: "request_changes", label: "Solicitar corrección" },
    ]),
  }),
});

const state = { incidentId: null, runId: null, generation: 0 };

const nodes = {};
const credentialStore = createMemoryCredentialStore();
const client = createAdministrativeApiClient({ credentialStore });

function byId(id) {
  return document.getElementById(id);
}

function cacheNodes() {
  [
    "review", "loading-state", "credential-section", "credential-form",
    "credential-input", "credential-error", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section",
    "fact-incident", "fact-run", "fact-state", "fact-workflow",
    "actions-section", "actions-list", "actions-empty",
    "refresh-button", "forget-credential",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function hideAll() {
  [
    "loading-state", "credential-section", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section", "actions-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["refresh-button"].hidden = true;
  nodes["forget-credential"].hidden = true;
}

function showError(kind) {
  hideAll();
  nodes[`error-${kind}`].hidden = false;
  nodes["review"].dataset.state = "error";
  nodes["refresh-button"].hidden = false;
  if (kind === "401" || kind === "403") nodes["forget-credential"].hidden = false;
}

function showKind(error) {
  if (!(error instanceof ApiClientError)) return "503";
  if (error.kind === "authentication") return "401";
  if (error.kind === "authorization") return "403";
  if (error.kind === "not_found") return "404";
  return "503";
}

function availableActions(workflowVersion, currentState) {
  const versions = REVIEW_ACTIONS[workflowVersion];
  if (!versions) return [];
  return versions[currentState] ?? [];
}

function renderContext(run, workflowVersion) {
  nodes["fact-incident"].textContent = state.incidentId;
  nodes["fact-run"].textContent = run.run_id;
  nodes["fact-state"].textContent = `${run.current_state ?? "—"} · ${run.status ?? "—"}`;
  nodes["fact-workflow"].textContent = workflowVersion;
  nodes["context-section"].hidden = false;
}

function renderActions(actions) {
  nodes["actions-list"].replaceChildren();
  actions.forEach((action) => {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = action.label;
    const meta = document.createElement("span");
    meta.className = "war-room__event-meta";
    meta.textContent = `${action.command} · transición ${action.transition} · resultado ${action.outcome}`;
    item.append(label, meta);
    nodes["actions-list"].append(item);
  });
  nodes["actions-empty"].hidden = actions.length > 0;
  nodes["actions-section"].hidden = false;
}

async function loadAll() {
  const generation = (state.generation += 1);
  hideAll();
  nodes["loading-state"].hidden = false;
  nodes["review"].dataset.state = "loading";
  try {
    const detail = await client.getIncident(state.incidentId);
    if (generation !== state.generation) return;
    const run = (detail.runs ?? []).find((entry) => entry.run_id === state.runId) ?? null;
    if (run === null) {
      showError("404");
      return;
    }
    renderContext(run, detail.workflow_version);
    renderActions(availableActions(detail.workflow_version, run.current_state));
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
    nodes["forget-credential"].hidden = false;
    nodes["review"].dataset.state = "ready";
  } catch (error) {
    if (generation !== state.generation) return;
    showError(showKind(error));
  }
}

function submitCredential(event) {
  event.preventDefault();
  const value = nodes["credential-input"].value;
  nodes["credential-input"].value = "";
  try {
    credentialStore.set(value);
  } catch {
    nodes["credential-error"].textContent = "Se requiere una API key no vacía.";
    nodes["credential-error"].hidden = false;
    return;
  }
  nodes["credential-error"].hidden = true;
  loadAll();
}

function forgetCredential() {
  state.generation += 1;
  credentialStore.clear();
  hideAll();
  nodes["credential-section"].hidden = false;
  nodes["review"].dataset.state = "auth";
}

document.addEventListener("DOMContentLoaded", () => {
  cacheNodes();
  nodes["refresh-button"].addEventListener("click", loadAll);
  nodes["forget-credential"].addEventListener("click", forgetCredential);
  nodes["credential-form"].addEventListener("submit", submitCredential);
  const params = new URLSearchParams(window.location.search);
  state.incidentId = params.get("incident_id");
  state.runId = params.get("run_id");
  if (!state.incidentId || !state.runId) {
    hideAll();
    nodes["error-missing-id"].hidden = false;
    nodes["review"].dataset.state = "error";
    return;
  }
  hideAll();
  nodes["credential-section"].hidden = false;
  nodes["review"].dataset.state = "auth";
});
