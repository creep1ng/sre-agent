import { ApiClientError } from "/public/api/client.js";
import { mountedView } from "/public/console/view.js";

// Acciones humanas del workflow 1.0.0, derivadas de los decision points publicados
// (mitigation_approval, stability_check) y de las transiciones de incident-response.yaml.
// La verificación y el cierre reutilizan la senda de comandos existente; su forma exacta
// queda sujeta al contrato run-command:2.1.0, que aún no está publicado (adaptación
// real pendiente, se documenta en el PR). Versión o estado desconocidos no ofrecen nada.
const REVIEW_ACTIONS = Object.freeze({
  "1.0.0": Object.freeze({
    mitigating: Object.freeze([
      { command: "approve_mitigation", transition: "apply_mitigation", outcome: "approve", label: "Aprobar mitigación", authorization: "run.approve" },
      { command: "reject_mitigation", transition: "reject_mitigation", outcome: "reject", label: "Rechazar mitigación", authorization: "run.approve" },
      { command: "request_changes", transition: "reject_mitigation", outcome: "request_changes", label: "Solicitar corrección", authorization: "run.command" },
    ]),
    verifying: Object.freeze([
      { command: "verification_passed", transition: "verification_passed", outcome: "stable", label: "Verificación estable", authorization: "run.command" },
      { command: "verification_failed", transition: "verification_failed", outcome: "not_stable", label: "Verificación no estable", authorization: "run.command" },
    ]),
    postmortem: Object.freeze([
      { command: "close_incident", transition: "close_incident", outcome: null, label: "Cerrar incidente", authorization: "run.approve", approval: true },
    ]),
  }),
});

const state = {
  incidentId: null,
  runId: null,
  incidentVersion: null,
  pending: null,
  idempotencyKey: null,
  generation: 0,
  submitting: false,
  commandInFlight: false,
  refreshAfterCommand: false,
  submissionComplete: false,
  draftComments: {},
};

const nodes = {};
const view = mountedView();
const client = view.client;

function byId(id) {
  return document.getElementById(id);
}

function cacheNodes() {
  [
    "review", "loading-state", "command-status", "error-missing-id", "error-401",
    "error-403", "error-404", "error-409", "error-503", "context-section",
    "fact-incident", "fact-run", "fact-incident-version", "fact-state", "fact-workflow",
    "actions-section", "actions-list", "actions-empty",
    "decision-section", "decision-title", "decision-form", "decision-comment",
    "decision-key", "decision-submit", "decision-approval", "decision-approval-row",
    "decision-hint",
    "receipt-section", "receipt-line",
    "refresh-button",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function hideAll() {
  [
    "loading-state", "command-status", "error-missing-id", "error-401",
    "error-403", "error-404", "error-409", "error-503", "context-section",
    "actions-section", "decision-section", "receipt-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["refresh-button"].hidden = true;
}

function showError(kind) {
  hideAll();
  nodes[`error-${kind}`].hidden = false;
  nodes["review"].dataset.state = "error";
  nodes["refresh-button"].hidden = false;
  view.focusIncident(null);
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
  nodes["fact-incident-version"].textContent = String(state.incidentVersion);
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
  nodes["decision-approval"].disabled = submitting;
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
  // El cierre exige una aprobación marcada en cada apertura: reabrir y confirmar
  // por accidente no puede cerrar el incidente ni heredar una revisión previa.
  nodes["decision-approval"].checked = false;
  nodes["decision-approval-row"].hidden = !action.approval;
  nodes["decision-hint"].hidden = !action.approval;
  syncApprovalGate(action);
  nodes["receipt-section"].hidden = true;
  nodes["decision-section"].hidden = false;
}

// La casilla es la aprobación explícita y visible del cierre; el botón no se
// habilita hasta que el usuario la marca en esta apertura del panel.
function syncApprovalGate(action) {
  nodes["decision-approval-row"].hidden = !action?.approval;
  nodes["decision-submit"].disabled = state.submitting || Boolean(action?.approval && !nodes["decision-approval"].checked);
}

// The identity is freshly resolved from this credential for each command; it
// is never persisted in UI state or browser storage.
function commandPayload(action, principalId) {
  const comment = nodes["decision-comment"].value.trim();
  return {
    command: action.command,
    expected_incident_version: state.incidentVersion,
    actor: "human",
    actor_reference: { reference_version: "1.0.0", principal_id: principalId },
    turn_id: null,
    disposition: null,
    comment: comment ? comment.slice(0, 2000) : null,
    authorization: {
      action: action.authorization,
      resource: { type: "incident_workflow", id: "incident-response" },
    },
  };
}

async function loadAll() {
  if (state.commandInFlight) {
    state.refreshAfterCommand = true;
    nodes["error-401"].hidden = true;
    nodes["command-status"].textContent =
      "El comando ya se envió y no se puede cancelar. El estado actual se consultará cuando termine.";
    nodes["command-status"].hidden = false;
    return;
  }
  if (state.submitting) return;
  const generation = (state.generation += 1);
  state.submissionComplete = false;
  state.incidentVersion = null;
  setSubmitting(false);
  hideAll();
  nodes["loading-state"].hidden = false;
  nodes["review"].dataset.state = "loading";
  try {
    const detail = await client.getIncident(state.incidentId);
    if (generation !== state.generation) return;
    if (!Number.isSafeInteger(detail.version) || detail.version < 0) {
      showError("503");
      return;
    }
    state.incidentVersion = detail.version;
    const run = (detail.runs ?? []).find((entry) => entry.run_id === state.runId) ?? null;
    if (run === null) {
      showError("404");
      return;
    }
    state.pending = null;
    renderContext(run, detail.workflow_version);
    renderActions(availableActions(detail.workflow_version, run.current_state));
    view.focusIncident(detail, run.run_id);
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
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
  let commandDispatched = false;
  try {
    const identity = await client.getWhoAmI();
    if (generation !== state.generation) return;
    state.commandInFlight = true;
    state.refreshAfterCommand = false;
    commandDispatched = true;
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
    if (commandDispatched) {
      state.commandInFlight = false;
      const refreshAfterCommand = state.refreshAfterCommand;
      state.refreshAfterCommand = false;
      setSubmitting(false);
      if (generation !== state.generation) {
        if (refreshAfterCommand) {
          void loadAll();
        } else {
          nodes["command-status"].textContent =
            "El comando enviado ya no está pendiente en el navegador. No se puede confirmar aquí si se aplicó. Autentícate y consulta el estado actual antes de decidir si lo reintentas.";
          nodes["command-status"].hidden = false;
        }
      }
    } else if (generation === state.generation) {
      setSubmitting(false);
      syncApprovalGate(state.pending);
    }
  }
}

// La credencial vive en la sesión de la consola. Un cambio o cierre descarta el contexto
// leído con la credencial anterior; un comando ya enviado conserva su bloqueo hasta terminar.
function dropSession() {
  state.generation += 1;
  state.pending = null;
  state.incidentVersion = null;
  state.draftComments = {};
  state.idempotencyKey = null;
  state.submissionComplete = false;
  state.refreshAfterCommand = false;
  if (!state.commandInFlight) setSubmitting(false);
  hideAll();
  nodes["error-401"].hidden = false;
  nodes["review"].dataset.state = "auth";
  if (state.commandInFlight) {
    nodes["command-status"].textContent =
      "El comando ya se envió y no se puede cancelar. El resultado no se mostrará en esta sesión; autentícate para consultar el estado actual cuando termine.";
    nodes["command-status"].hidden = false;
  }
}

cacheNodes();
nodes["refresh-button"].addEventListener("click", loadAll);
nodes["decision-form"].addEventListener("submit", submitDecision);
nodes["decision-approval"].addEventListener("change", () => syncApprovalGate(state.pending));
state.incidentId = view.params.get("incident_id");
state.runId = view.params.get("run_id");
if (!state.incidentId || !state.runId) {
  hideAll();
  nodes["error-missing-id"].hidden = false;
  nodes["review"].dataset.state = "error";
  // Sin run no hay lectura posible: la franja no conserva el incidente de una vista anterior.
  view.focusIncident(null);
} else {
  view.onSession((session) => (session.phase === "active" ? loadAll() : dropSession()));
}
