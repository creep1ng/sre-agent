import {
  ApiClientError,
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

// Fixture de PRESENTACIÓN con la forma de $defs/postmortem
// (incident-state.schema.yaml): estado real draft, sin versión ni endpoint
// porque #335 no existe. Nunca se presenta como artefacto persistido.
const PRESENTATION_FIXTURE = Object.freeze({
  postmortem_id: "pm_demo0001",
  status: "draft",
  created_by: "human",
  created_at: "2026-08-24T14:30:00Z",
  summary: "Checkout failing at payment; incident declared after triage.",
  impact: null,
  root_cause: null,
  resolution: null,
  lessons: [],
});

const UNKNOWN = "Desconocido (no registrado)";
const PENDING = "Pendiente";

const state = { incidentId: null, generation: 0 };

const nodes = {};
const credentialStore = createMemoryCredentialStore();
const client = createAdministrativeApiClient({ credentialStore });

function byId(id) {
  return document.getElementById(id);
}

function cacheNodes() {
  [
    "postmortem", "loading-state", "credential-section", "credential-form",
    "credential-input", "credential-error", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section", "fact-incident",
    "fact-state", "fact-artifact", "fixture-banner",
    "artifact-section", "artifact-sections",
    "refresh-button", "forget-credential",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function hideAll() {
  [
    "loading-state", "credential-section", "error-missing-id", "error-401",
    "error-403", "error-404", "error-503", "context-section", "artifact-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["refresh-button"].hidden = true;
  nodes["forget-credential"].hidden = true;
}

function showError(kind) {
  hideAll();
  nodes[`error-${kind}`].hidden = false;
  nodes["postmortem"].dataset.state = "error";
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

function sectionRow(title, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = title;
  const definition = document.createElement("dd");
  definition.textContent = value;
  wrapper.append(term, definition);
  return wrapper;
}

function renderArtifact(detail) {
  const draft = PRESENTATION_FIXTURE;
  nodes["fact-incident"].textContent = state.incidentId;
  nodes["fact-state"].textContent = detail.state;
  nodes["fact-artifact"].textContent = `${draft.postmortem_id} · ${draft.status} · sin versionado contractual`;
  nodes["fixture-banner"].textContent =
    "Sin artefacto persistido en el backend (#335 pendiente): abajo, fixture de presentación.";
  nodes["fixture-banner"].hidden = false;
  nodes["context-section"].hidden = false;
  const sections = nodes["artifact-sections"];
  sections.replaceChildren();
  [
    ["Resumen", draft.summary],
    ["Impacto conocido", draft.impact ?? UNKNOWN],
    ["Hipotesis o causa", draft.root_cause ?? UNKNOWN],
    ["Certeza", PENDING],
    ["Estrategia", PENDING],
    ["Resolucion", draft.resolution ?? UNKNOWN],
    ["Verificacion", PENDING],
    ["Pendientes", draft.lessons.length === 0 ? "Sin lecciones registradas" : draft.lessons.join("; ")],
  ].forEach(([title, value]) => sections.append(sectionRow(title, value)));
  nodes["artifact-section"].hidden = false;
}

async function loadAll() {
  const generation = (state.generation += 1);
  hideAll();
  nodes["loading-state"].hidden = false;
  nodes["postmortem"].dataset.state = "loading";
  try {
    const detail = await client.getIncident(state.incidentId);
    if (generation !== state.generation) return;
    renderArtifact(detail);
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
    nodes["forget-credential"].hidden = false;
    nodes["postmortem"].dataset.state = "ready";
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
  nodes["postmortem"].dataset.state = "auth";
}

document.addEventListener("DOMContentLoaded", () => {
  cacheNodes();
  nodes["refresh-button"].addEventListener("click", loadAll);
  nodes["forget-credential"].addEventListener("click", forgetCredential);
  nodes["credential-form"].addEventListener("submit", submitCredential);
  state.incidentId = new URLSearchParams(window.location.search).get("incident_id");
  if (!state.incidentId) {
    hideAll();
    nodes["error-missing-id"].hidden = false;
    nodes["postmortem"].dataset.state = "error";
    return;
  }
  hideAll();
  nodes["credential-section"].hidden = false;
  nodes["postmortem"].dataset.state = "auth";
});
