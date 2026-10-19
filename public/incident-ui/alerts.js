import { mountedView } from "../console/view.js";

(() => {
  "use strict";

  const view = mountedView();

  const FIXTURE_PATHS = Object.freeze({
    default: "/public/fixtures/alerts.json",
    empty: "/public/fixtures/alerts-empty.json",
  });
  // Live alerts come from GET /v1/alerts (gateway rules over governed MCP); fixtures only on request.
  const LIVE_POLL_MS = 15000;
  const CONTEXT_FIELDS = Object.freeze(["service", "summary", "observed_at", "source", "severity"]);
  const LIVE_SEVERITY = Object.freeze({ sev1: "critical", sev2: "warning", sev3: "info", sev4: "info" });

  const severityMeta = Object.freeze({
    critical: { label: "SEV1 · Crítica", tone: "critical", rank: 3 },
    warning: { label: "SEV2 · Alta", tone: "warning", rank: 2 },
    info: { label: "SEV3 · Media", tone: "info", rank: 1 },
  });

  const statusMeta = Object.freeze({
    new: { label: "Nueva", tone: "info" },
    acknowledged: { label: "Reconocida", tone: "warning" },
    monitoring: { label: "En observación", tone: "success" },
  });

  const state = {
    alerts: [],
    selectedAlertId: null,
    countNoun: "simuladas",
  };
  let pollTimer = null;
  let lastLiveAt = null;

  const nodes = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function cacheNodes() {
    [
      "alert-inbox",
      "source-mode",
      "fixture-label",
      "load-error",
      "load-error-title",
      "load-error-detail",
      "live-locked",
      "loading-state",
      "alert-list",
      "alert-count",
      "empty-state",
      "detail-placeholder",
      "detail-content",
      "detail-title",
      "detail-summary",
      "detail-severity",
      "detail-status",
      "detail-service",
      "detail-timestamp",
      "detail-source",
      "detail-id",
      "detail-context",
      "origin-section",
      "detail-origin-summary",
      "origin-metadata",
      "start-triage",
      "triage-feedback",
      "triage-feedback-detail",
    ].forEach((id) => {
      nodes[id] = byId(id);
    });
  }

  function getFixtureKey() {
    const requested = view.params.get("fixture");
    return Object.hasOwn(FIXTURE_PATHS, requested) ? requested : null;
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

  function severityFor(alert) {
    return severityMeta[alert.severity] ?? severityMeta.info;
  }

  function statusFor(alert) {
    return statusMeta[alert.status] ?? { label: alert.status, tone: "info" };
  }

  function sortAlerts(alerts) {
    return [...alerts].sort((a, b) => {
      const severityDelta = severityFor(b).rank - severityFor(a).rank;
      if (severityDelta !== 0) return severityDelta;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });
  }

  function validateFixture(payload) {
    if (!payload || !Array.isArray(payload.alerts)) {
      throw new Error("Fixture inválido: se esperaba una propiedad alerts de tipo array.");
    }

    const required = [
      "alert_id",
      "title",
      "summary",
      "service",
      "severity",
      "timestamp",
      "status",
      "source",
      "context",
    ];

    payload.alerts.forEach((alert, index) => {
      const missing = required.filter((field) => !alert[field]);
      if (missing.length > 0) {
        throw new Error(`Fixture inválido en alerts[${index}]: faltan ${missing.join(", ")}.`);
      }
    });

    return payload.alerts;
  }

  function renderAlertList() {
    nodes["alert-list"].replaceChildren();

    if (state.alerts.length === 0) {
      nodes["alert-list"].hidden = true;
      nodes["empty-state"].hidden = false;
      nodes["alert-count"].textContent = "0 alertas pendientes";
      clearDetail();
      return;
    }

    nodes["empty-state"].hidden = true;
    nodes["alert-list"].hidden = false;
    nodes["alert-count"].textContent = `${state.alerts.length} alertas ${state.countNoun}`;

    state.alerts.forEach((alert) => {
      const severity = severityFor(alert);
      const status = statusFor(alert);
      const item = document.createElement("li");
      const button = document.createElement("button");
      const topRow = document.createElement("span");
      const severityBadge = document.createElement("span");
      const statusText = document.createElement("span");
      const title = document.createElement("strong");
      const summary = document.createElement("span");
      const metadata = document.createElement("span");
      const service = document.createElement("span");
      const timestamp = document.createElement("time");

      item.className = "alert-list__item";
      button.className = "alert-list__button";
      button.type = "button";
      button.dataset.alertId = alert.alert_id;
      button.setAttribute("aria-pressed", String(state.selectedAlertId === alert.alert_id));
      if (state.selectedAlertId === alert.alert_id) {
        button.dataset.selected = "true";
      }

      topRow.className = "alert-list__top-row";
      severityBadge.className = "ma-badge";
      severityBadge.dataset.tone = severity.tone;
      severityBadge.textContent = severity.label;
      statusText.className = "ma-badge alert-list__status";
      statusText.dataset.tone = status.tone;
      statusText.textContent = status.label;
      topRow.append(severityBadge, statusText);

      title.className = "alert-list__title";
      title.textContent = alert.title;
      summary.className = "alert-list__summary";
      summary.textContent = alert.summary;

      metadata.className = "alert-list__metadata";
      service.className = "";
      service.textContent = alert.service;
      timestamp.dateTime = alert.timestamp;
      timestamp.textContent = formatTimestamp(alert.timestamp);
      metadata.append(service, timestamp);

      button.append(topRow, title, summary, metadata);
      button.addEventListener("click", () => selectAlert(alert.alert_id));
      item.append(button);
      nodes["alert-list"].append(item);
    });
  }

  function renderOrigin(origin) {
    nodes["origin-metadata"].replaceChildren();

    if (!origin) {
      nodes["origin-section"].hidden = true;
      return;
    }

    nodes["origin-section"].hidden = false;
    nodes["detail-origin-summary"].textContent = origin.summary ?? "Metadata de origen disponible.";

    const metadata = origin.metadata && typeof origin.metadata === "object" ? origin.metadata : {};
    Object.entries(metadata).forEach(([key, value]) => {
      const wrapper = document.createElement("div");
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = key;
      description.textContent = String(value);
      wrapper.append(term, description);
      nodes["origin-metadata"].append(wrapper);
    });
  }

  function renderDetail(alert) {
    const severity = severityFor(alert);
    const status = statusFor(alert);

    nodes["detail-placeholder"].hidden = true;
    nodes["detail-content"].hidden = false;
    nodes["triage-feedback"].hidden = true;

    nodes["detail-title"].textContent = alert.title;
    nodes["detail-summary"].textContent = alert.summary;
    nodes["detail-severity"].textContent = severity.label;
    nodes["detail-severity"].dataset.tone = severity.tone;
    nodes["detail-status"].textContent = status.label;
    nodes["detail-status"].dataset.tone = status.tone;
    nodes["detail-service"].textContent = alert.service;
    nodes["detail-timestamp"].textContent = formatTimestamp(alert.timestamp);
    nodes["detail-source"].textContent = alert.source;
    nodes["detail-id"].textContent = alert.alert_id;
    nodes["detail-context"].textContent = alert.context;
    nodes["start-triage"].dataset.alertId = alert.alert_id;

    renderOrigin(alert.origin);
  }

  function clearDetail() {
    state.selectedAlertId = null;
    nodes["detail-content"].hidden = true;
    nodes["detail-placeholder"].hidden = false;
    nodes["triage-feedback"].hidden = true;
  }

  function selectAlert(alertId) {
    const alert = state.alerts.find((candidate) => candidate.alert_id === alertId);
    if (!alert) return;

    state.selectedAlertId = alertId;
    renderAlertList();
    renderDetail(alert);
  }

  // Intención manual de triage (contrato Sprint 1, HU-OPS-01).
  // El auto-triage por umbral del plano de control está bloqueado por falta
  // de contrato: ver docs/hu-ops-01-threshold-contract-pending.md. No
  // hardcodear un threshold aquí.
  function emitTriageRequest() {
    const alertId = nodes["start-triage"].dataset.alertId;
    const alert = state.alerts.find((candidate) => candidate.alert_id === alertId);
    if (!alert) return;

    const event = new CustomEvent("midnight:triage-requested", {
      bubbles: true,
      detail: Object.freeze({
        alert_id: alert.alert_id,
        service: alert.service,
        source: "hu-ops-01-alert-inbox",
        handoff: alert.handoff ?? {},
      }),
    });

    nodes["start-triage"].dispatchEvent(event);
    nodes["triage-feedback-detail"].textContent =
      `Se emitió midnight:triage-requested para ${alert.alert_id}. No se creó ni asoció un incidente.`;
    nodes["triage-feedback"].hidden = false;
  }

  function openTriageForRequestedAlert(event) {
    const alertId = event.detail?.alert_id;
    if (typeof alertId !== "string" || !/^[a-z][a-z0-9_-]{2,63}$/.test(alertId)) return;
    view.navigate("triage", { ...event.detail.handoff, alert_id: alertId });
  }

  function showLoadError(error, title, detail, countLabel = "Fixture no disponible") {
    // Live failures are shown in the inbox and retried; only a broken fixture is a console error.
    if (!title) console.error(error);
    nodes["loading-state"].hidden = true;
    nodes["live-locked"].hidden = true;
    nodes["alert-list"].hidden = true;
    nodes["empty-state"].hidden = true;
    if (title) nodes["load-error-title"].textContent = title;
    if (detail) nodes["load-error-detail"].textContent = detail;
    nodes["load-error"].hidden = false;
    nodes["alert-count"].textContent = countLabel;
    nodes["alert-inbox"].dataset.state = "error";
    clearDetail();
  }

  function showAlerts(alerts) {
    state.alerts = sortAlerts(alerts);
    nodes["loading-state"].hidden = true;
    nodes["live-locked"].hidden = true;
    nodes["load-error"].hidden = true;
    nodes["alert-inbox"].dataset.state = state.alerts.length === 0 ? "empty" : "ready";
    const kept = state.alerts.find((alert) => alert.alert_id === state.selectedAlertId);
    const selected = kept ?? state.alerts[0];
    state.selectedAlertId = selected?.alert_id ?? null;
    renderAlertList();
    if (selected) renderDetail(selected);
  }

  async function loadFixture(fixturePath) {
    nodes["fixture-label"].textContent = fixturePath.split("/").at(-1);

    try {
      const response = await fetch(fixturePath, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`No se pudo cargar ${fixturePath}: HTTP ${response.status}.`);
      }

      showAlerts(validateFixture(await response.json()));
    } catch (error) {
      showLoadError(error);
    }
  }

  // Canonical alert (incident-state $defs/alert) to the inbox card; the API stays authoritative.
  function fromLive(alert, evaluatedAt) {
    const origin = alert.origin && typeof alert.origin === "object" ? alert.origin : {};
    return {
      alert_id: alert.alert_id,
      title: alert.summary,
      summary: origin.condition ?? alert.summary,
      service: alert.service,
      severity: LIVE_SEVERITY[alert.severity] ?? "info",
      timestamp: alert.observed_at,
      status: alert.status,
      source: alert.source,
      // Canonical facts handed to Triage as a prefill; the operator still confirms them there.
      handoff: Object.fromEntries(CONTEXT_FIELDS.map((field) => [`ctx_${field}`, alert[field]])),
      context:
        "Regla evaluada por el gateway con query_prometheus a través del MCP gobernado (auditado). " +
        `Última evaluación: ${formatTimestamp(evaluatedAt)}. Severidad sugerida: ${alert.severity}.`,
      origin: {
        summary: "Señal y condición que reportó la regla en vivo.",
        metadata: {
          signal: origin.signal,
          condition: origin.condition,
          detector: origin.detector,
          evaluated_at: origin.observed_at,
        },
      },
    };
  }

  function describeLiveError(error) {
    if (error?.kind === "authorization")
      return ["Sin acceso a alertas en vivo", "Esta identidad necesita alert.read sobre incident-response y mcp.invoke sobre query_prometheus."];
    if (error?.status === 503 || error?.kind === "network")
      return ["Fuente de alertas no disponible", "El MCP gobernado no respondió. Se reintenta automáticamente."];
    return ["Respuesta de alertas inválida", "La fuente de métricas devolvió un resultado que no se puede evaluar. Se reintenta automáticamente."];
  }

  async function pollLive() {
    clearTimeout(pollTimer);
    try {
      const payload = await view.client.listAlerts();
      if (view.signal.aborted || view.session.phase !== "active") return;
      if (!payload || !Array.isArray(payload.alerts)) throw new Error("GET /v1/alerts devolvió un cuerpo inválido.");
      lastLiveAt = payload.evaluated_at;
      nodes["fixture-label"].textContent = `GET /v1/alerts · ${formatTimestamp(payload.evaluated_at)}`;
      showAlerts(payload.alerts.map((alert) => fromLive(alert, payload.evaluated_at)));
    } catch (error) {
      // A 401 already ended the session (locked state); do not paint an error over it.
      if (view.signal.aborted || view.session.phase !== "active") return;
      const [title, detail] = describeLiveError(error);
      // A transient failure keeps the last list on screen; a denial or a never-loaded inbox does not.
      if (lastLiveAt && error?.kind !== "authorization") {
        nodes["fixture-label"].textContent = `${title}: reintentando · última lectura ${formatTimestamp(lastLiveAt)}`;
      } else {
        showLoadError(error, title, detail, "Alertas en vivo no disponibles");
      }
    }
    if (!view.signal.aborted && view.session.phase === "active") {
      pollTimer = setTimeout(pollLive, LIVE_POLL_MS);
    }
  }

  function startLive() {
    state.countNoun = "en vivo";
    nodes["source-mode"].textContent = "En vivo";
    nodes["fixture-label"].textContent = "GET /v1/alerts";
    view.signal.addEventListener("abort", () => clearTimeout(pollTimer), { once: true });
    view.onSession((session) => {
      clearTimeout(pollTimer);
      if (session.phase === "active") {
        pollLive();
        return;
      }
      state.alerts = [];
      lastLiveAt = null;
      clearDetail();
      nodes["loading-state"].hidden = true;
      nodes["load-error"].hidden = true;
      nodes["alert-list"].hidden = true;
      nodes["empty-state"].hidden = true;
      nodes["live-locked"].hidden = false;
      nodes["alert-count"].textContent = "Conecta la consola para leer alertas en vivo";
      nodes["alert-inbox"].dataset.state = "locked";
    });
  }

  cacheNodes();
  nodes["start-triage"].addEventListener("click", emitTriageRequest);
  document.addEventListener("midnight:triage-requested", openTriageForRequestedAlert, {
    signal: view.signal,
  });
  const fixtureKey = getFixtureKey();
  if (fixtureKey) loadFixture(FIXTURE_PATHS[fixtureKey]);
  else startLive();
})();
