import {
  ApiClientError,
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const THEME_STORAGE_KEY = "midnight-agent-theme";
const TIMELINE_LIMIT = 50;

const severityTones = Object.freeze({
  sev1: "critical",
  sev2: "warning",
  sev3: "info",
  sev4: "info",
});

const eventKindTones = Object.freeze({
  denial: "critical",
  escalation: "critical",
  human_command: "warning",
  mitigation_proposed: "warning",
  run_terminated: "success",
});

const state = {
  incidentId: null,
  runId: null,
  cursor: null,
  hasMore: false,
  eventCount: 0,
  version: null,
  generation: 0,
};

const nodes = {};
const credentialStore = createMemoryCredentialStore();
const client = createAdministrativeApiClient({ credentialStore });

function byId(id) {
  return document.getElementById(id);
}

function cacheNodes() {
  [
    "war-room",
    "loading-state",
    "credential-section",
    "credential-form",
    "credential-input",
    "credential-error",
    "error-missing-id",
    "error-401",
    "error-403",
    "error-404",
    "error-503",
    "summary-section",
    "incident-title",
    "version-line",
    "incident-state",
    "incident-severity",
    "fact-id",
    "fact-severity",
    "fact-impact",
    "fact-snapshot",
    "approvals-empty",
    "approvals-list",
    "timeline-section",
    "timeline-count",
    "timeline-list",
    "timeline-empty",
    "load-more",
    "refresh-button",
    "forget-credential",
    "theme-toggle",
    "theme-switch-label",
  ].forEach((id) => {
    nodes[id] = byId(id);
  });
}

function getCurrentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function syncThemeSwitch() {
  const isDark = getCurrentTheme() === "dark";
  nodes["theme-toggle"].setAttribute("aria-checked", String(isDark));
  nodes["theme-toggle"].setAttribute(
    "aria-label",
    isDark ? "Cambiar a tema claro" : "Cambiar a tema oscuro",
  );
  nodes["theme-switch-label"].textContent = isDark ? "Oscuro" : "Claro";
}

function toggleTheme() {
  const nextTheme = getCurrentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = nextTheme;

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  } catch {
    // El cambio de tema sigue funcionando aunque el navegador bloquee storage.
  }

  syncThemeSwitch();
}

function formatTimestamp(timestamp) {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }

  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
    hour12: false,
  }).format(parsed);
}

function hideAll() {
  [
    "loading-state",
    "credential-section",
    "error-missing-id",
    "error-401",
    "error-403",
    "error-404",
    "error-503",
    "summary-section",
    "timeline-section",
  ].forEach((id) => {
    nodes[id].hidden = true;
  });
  nodes["refresh-button"].hidden = true;
  nodes["forget-credential"].hidden = true;
}

function showError(kind, status) {
  hideAll();
  nodes[`error-${kind}`].hidden = false;
  nodes["war-room"].dataset.state = "error";
  if (kind === "401") {
    nodes["credential-section"].hidden = false;
  }
  // Toda vista de error conserva una vía de recuperación: reintentar con
  // Actualizar y, ante 401/403, cambiar u olvidar la credencial.
  nodes["refresh-button"].hidden = false;
  if (kind === "401" || kind === "403") {
    nodes["forget-credential"].hidden = false;
  }
  console.error(`War room failed: HTTP ${status}`);
}

function newGeneration() {
  state.generation += 1;
  return state.generation;
}

function clearSessionData() {
  nodes["timeline-list"].replaceChildren();
  nodes["load-more"].disabled = false;
  state.runId = null;
  state.cursor = null;
  state.hasMore = false;
  state.eventCount = 0;
  state.version = null;
}

function latestRunId(detail) {
  const runs = Array.isArray(detail.runs) ? detail.runs : [];
  if (runs.length === 0) return null;
  const runId = runs[runs.length - 1].run_id;
  return typeof runId === "string" ? runId : null;
}

function actorLabel(actor) {
  if (!actor || typeof actor !== "object") return "sistema";
  const reference = actor.reference;
  if (reference && typeof reference.principal_id === "string") {
    return `${actor.type} · ${reference.principal_id}`;
  }
  return String(actor.type ?? "sistema");
}

function renderSummary(detail, snapshot) {
  nodes["incident-title"].textContent =
    detail.alert?.summary ?? `Incidente ${detail.incident_id}`;
  nodes["version-line"].textContent =
    `Versión ${detail.version} · actualizado ${formatTimestamp(detail.updated_at)}`;
  nodes["incident-state"].textContent = detail.state;
  nodes["incident-state"].dataset.tone = "info";
  nodes["incident-severity"].textContent = detail.severity ?? "sin severidad";
  nodes["incident-severity"].dataset.tone = severityTones[detail.severity] ?? "info";
  nodes["fact-id"].textContent = detail.incident_id;
  nodes["fact-severity"].textContent = detail.severity ?? "—";
  nodes["fact-impact"].textContent = detail.impact ?? "—";
  if (snapshot) {
    nodes["fact-snapshot"].textContent =
      `v${snapshot.version} (seq ${snapshot.event_sequence})`;
  } else {
    nodes["fact-snapshot"].textContent = "Sin snapshot todavía";
  }

  nodes["approvals-list"].replaceChildren();
  const approvals = Array.isArray(detail.approvals) ? detail.approvals : [];
  nodes["approvals-empty"].hidden = approvals.length > 0;
  approvals.forEach((approval) => {
    const item = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "ma-badge";
    badge.dataset.tone = approval.granted ? "success" : "critical";
    badge.textContent = approval.granted ? "Aprobado" : "Rechazado";
    const text = document.createElement("span");
    text.textContent = `${approval.subject_id} · ${formatTimestamp(approval.decided_at)}`;
    item.append(badge, text);
    nodes["approvals-list"].append(item);
  });

  nodes["summary-section"].hidden = false;
}

function renderEvents(events, { append } = {}) {
  if (!append) {
    nodes["timeline-list"].replaceChildren();
    state.eventCount = 0;
  }

  events.forEach((event) => {
    const item = document.createElement("li");
    item.className = "war-room__event";
    const badge = document.createElement("span");
    badge.className = "ma-badge";
    badge.dataset.tone = eventKindTones[event.kind] ?? "info";
    badge.textContent = event.kind;
    const summary = document.createElement("strong");
    summary.textContent = event.summary ?? "Evento registrado.";
    const meta = document.createElement("span");
    meta.className = "war-room__event-meta";
    meta.textContent =
      `${actorLabel(event.actor)} · ${formatTimestamp(event.occurred_at)} · seq ${event.sequence}`;
    item.append(badge, summary, meta);
    nodes["timeline-list"].append(item);
    state.eventCount += 1;
  });

  nodes["timeline-empty"].hidden = state.eventCount > 0;
  nodes["timeline-count"].textContent =
    state.eventCount === 1 ? "1 evento" : `${state.eventCount} eventos`;
  nodes["timeline-section"].hidden = false;
}

async function fetchTimeline({ runId, after } = {}) {
  return client.getIncidentTimeline(state.incidentId, {
    runId,
    after,
    limit: TIMELINE_LIMIT,
  });
}

async function loadAll() {
  const generation = newGeneration();
  clearSessionData();
  hideAll();
  nodes["loading-state"].hidden = false;
  nodes["war-room"].dataset.state = "loading";

  try {
    const detail = await client.getIncident(state.incidentId);
    // El run queda fijado desde el detalle: el cursor seq:N solo tiene
    // sentido dentro de un mismo run. Actualizar re-deriva el último run y
    // reinicia la paginación.
    if (generation !== state.generation) return;
    const runId = latestRunId(detail);
    let timeline;
    try {
      timeline = await fetchTimeline({ runId });
    } catch (error) {
      if (!(error instanceof ApiClientError) || error.code !== "run_absent") throw error;
      // Incidente sin runs: timeline explícitamente vacío, no es un error.
      timeline = { events: [], next_cursor: "seq:-1", has_more: false };
    }
    let snapshot = null;
    try {
      snapshot = await client.getIncidentSnapshot(state.incidentId, { runId });
    } catch (error) {
      if (!(error instanceof ApiClientError) || error.status !== 404) throw error;
      // Ausencia explícita de snapshot: se muestra sin snapshot, no es fatal.
    }

    if (generation !== state.generation) return;
    state.runId = runId;
    state.cursor = timeline.next_cursor;
    state.hasMore = timeline.has_more === true;
    state.version = detail.version;
    renderSummary(detail, snapshot);
    renderEvents(timeline.events ?? []);
    nodes["load-more"].hidden = !state.hasMore;
    nodes["loading-state"].hidden = true;
    nodes["refresh-button"].hidden = false;
    nodes["forget-credential"].hidden = false;
    nodes["war-room"].dataset.state = "ready";
  } catch (error) {
    if (generation !== state.generation) return;
    if (error instanceof ApiClientError) {
      if (error.kind === "authentication") showError("401", error.status);
      else if (error.kind === "authorization") showError("403", error.status);
      else if (error.kind === "conflict") showError("503", error.status);
      else if (error.status === 404) showError("404", error.status);
      else showError("503", error.status ?? "desconocido");
    } else {
      showError("503", "desconocido");
    }
  }
}

async function loadMore() {
  const generation = state.generation;
  nodes["load-more"].disabled = true;
  try {
    const page = await fetchTimeline({ runId: state.runId, after: state.cursor });
    // Una respuesta de una sesión/carga anterior nunca muta la vista actual.
    if (generation !== state.generation) return;
    state.cursor = page.next_cursor;
    state.hasMore = page.has_more === true;
    renderEvents(page.events ?? [], { append: true });
    nodes["load-more"].hidden = !state.hasMore;
  } catch (error) {
    if (generation !== state.generation) return;
    if (error instanceof ApiClientError) {
      // Tras una denegación no queda contenido protegido visible.
      if (error.kind === "authentication") showError("401", error.status);
      else if (error.kind === "authorization") showError("403", error.status);
      else showError("503", error.status ?? "desconocido");
    } else {
      showError("503", "desconocido");
    }
  } finally {
    if (generation === state.generation) nodes["load-more"].disabled = false;
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
  newGeneration();
  credentialStore.clear();
  clearSessionData();
  hideAll();
  nodes["credential-section"].hidden = false;
  nodes["war-room"].dataset.state = "auth";
}

document.addEventListener("DOMContentLoaded", () => {
  cacheNodes();
  syncThemeSwitch();
  nodes["theme-toggle"].addEventListener("click", toggleTheme);
  nodes["refresh-button"].addEventListener("click", loadAll);
  nodes["load-more"].addEventListener("click", loadMore);
  nodes["forget-credential"].addEventListener("click", forgetCredential);
  nodes["credential-form"].addEventListener("submit", submitCredential);

  const incidentId = new URLSearchParams(window.location.search).get("incident_id");
  if (!incidentId) {
    hideAll();
    nodes["error-missing-id"].hidden = false;
    nodes["war-room"].dataset.state = "error";
    return;
  }
  state.incidentId = incidentId;
  hideAll();
  nodes["credential-section"].hidden = false;
  nodes["war-room"].dataset.state = "auth";
});
