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

const state = { incidentId: null, runId: null, pending: null, idempotencyKey: null, generation: 0, submitting: false, submissionComplete: false, draftComments: {} };

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
    "error-403", "error-404", "error-409", "error-503", "context-section",
    "fact-incident", "fact-run", "fact-state", "fact-workflow",
    "actions-section", "actions-list", "actions-empty",
    "decision-section", "decision-title", "decision-form", "decision-comment",
    "decision-key", "decision-submit", "receipt-section", "receipt-line",
    "refresh-button", "forget-credential",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function hideAll() {
  [
    "loading-state", "credential-section", "error-missing-id", "error-401",
    "error-403", "error-404", "error-409", "error-503", "context-section",
    "actions-section", "decision-section", "receipt-section",
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
  if (error.kind === "conflict") return "409";
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
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ma-button ma-button--secondary";
    button.textContent = action.label;
    button.dataset.command = action.command;
    button.addEventListener("click", () => openDecision(action));
    item.append(button);
    nodes["actions-list"].append(item);
  });
  nodes["actions-empty"].hidden = actions.length > 0;
  nodes["actions-section"].hidden = false;
}

function setSubmitting(submitting) {
  state.submitting = submitting;
  nodes["refresh-button"].disabled = submitting;
  nodes["decision-submit"].disabled = submitting;
  nodes["decision-comment"].disabled = submitting;
  nodes["actions-list"].querySelectorAll("button").forEach((button) => {
    button.disabled = submitting || state.submissionComplete;
  });
}

function openDecision(action) {
  if (state.submitting || state.submissionComplete) return;
  if (state.pending) state.draftComments[state.pending.command] = nodes["decision-comment"].value;
  state.pending = action;
  state.idempotencyKey = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-review`;
  nodes["decision-title"].textContent = action.label;
  nodes["decision-comment"].value = state.draftComments[action.command] ?? "";
  nodes["decision-key"].textContent = state.idempotencyKey;
  nodes["decision-submit"].disabled = false;
  nodes["receipt-section"].hidden = true;
  nodes["decision-section"].hidden = false;
}

// The identity is freshly resolved from this credential for each command; it
// is never persisted in UI state or browser storage.
function commandPayload(action, principalId) {
  const comment = nodes["decision-comment"].value.trim();
  return {
    command: action.command,
    actor: "human",
    actor_reference: { reference_version: "1.0.0", principal_id: principalId },
    turn_id: null,
    disposition: null,
    comment: comment ? comment.slice(0, 2000) : null,
    authorization: {
      action: action.command === "request_changes" ? "run.command" : "run.approve",
      resource: { type: "incident_workflow", id: "incident-response" },
    },
  };
}

async function loadAll() {
  if (state.submitting) return;
  const generation = (state.generation += 1);
  state.submissionComplete = false;
  setSubmitting(false);
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
    state.pending = null;
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

async function submitDecision(event) {
  event.preventDefault();
  const action = state.pending;
  if (!action || state.submitting || state.submissionComplete) return;
  const generation = state.generation;
  state.draftComments[action.command] = nodes["decision-comment"].value;
  setSubmitting(true);
  try {
    const identity = await client.getWhoAmI();
    if (generation !== state.generation) return;
    const response = await client.sendRunCommand(
      state.incidentId,
      state.runId,
      commandPayload(action, identity.principal_id),
      state.idempotencyKey,
    );
    if (generation !== state.generation) return;
    state.submissionComplete = true;
    nodes["receipt-line"].textContent =
      `Decisión ${action.command} registrada por el backend (transición ${action.transition}, ` +
      `resultado ${action.outcome}). Estado del run: ${response.current_state ?? "—"}.`;
    nodes["decision-section"].hidden = true;
    nodes["receipt-section"].hidden = false;
  } catch (error) {
    if (generation !== state.generation) return;
    if (error instanceof ApiClientError) showError(showKind(error));
    else showError("503");
  } finally {
    if (generation === state.generation) setSubmitting(false);
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
  state.pending = null;
  state.draftComments = {};
  state.idempotencyKey = null;
  state.submissionComplete = false;
  setSubmitting(false);
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
  nodes["decision-form"].addEventListener("submit", submitDecision);
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
