(() => {
  "use strict";

  const THEME_STORAGE_KEY = "midnight-agent-theme";

  const FIXTURE_PATHS = Object.freeze({
    default: "/public/fixtures/alerts.json",
    empty: "/public/fixtures/alerts-empty.json",
  });

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
  };

  const nodes = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function cacheNodes() {
    [
      "alert-inbox",
      "fixture-label",
      "load-error",
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

  function getFixtureKey() {
    const requested = new URLSearchParams(window.location.search).get("fixture");
    return requested === "empty" ? "empty" : "default";
  }

  function getFixturePath() {
    return FIXTURE_PATHS[getFixtureKey()];
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
    nodes["alert-count"].textContent = `${state.alerts.length} alertas simuladas`;

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
      statusText.className = "alert-list__status";
      statusText.textContent = status.label;
      topRow.append(severityBadge, statusText);

      title.className = "alert-list__title";
      title.textContent = alert.title;
      summary.className = "alert-list__summary";
      summary.textContent = alert.summary;

      metadata.className = "alert-list__metadata";
      service.className = "ma-mono";
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
      }),
    });

    nodes["start-triage"].dispatchEvent(event);
    nodes["triage-feedback-detail"].textContent =
      `Se emitió midnight:triage-requested para ${alert.alert_id}. No se creó ni asoció un incidente.`;
    nodes["triage-feedback"].hidden = false;
  }

  function showLoadError(error) {
    console.error(error);
    nodes["loading-state"].hidden = true;
    nodes["alert-list"].hidden = true;
    nodes["empty-state"].hidden = true;
    nodes["load-error"].hidden = false;
    nodes["alert-count"].textContent = "Fixture no disponible";
    nodes["alert-inbox"].dataset.state = "error";
    clearDetail();
  }

  async function loadAlerts() {
    const fixturePath = getFixturePath();
    nodes["fixture-label"].textContent = fixturePath.split("/").at(-1);

    try {
      const response = await fetch(fixturePath, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`No se pudo cargar ${fixturePath}: HTTP ${response.status}.`);
      }

      const payload = await response.json();
      state.alerts = sortAlerts(validateFixture(payload));
      nodes["loading-state"].hidden = true;
      nodes["load-error"].hidden = true;
      nodes["alert-inbox"].dataset.state = state.alerts.length === 0 ? "empty" : "ready";

      if (state.alerts.length > 0) {
        state.selectedAlertId = state.alerts[0].alert_id;
      }

      renderAlertList();
      if (state.selectedAlertId) {
        renderDetail(state.alerts[0]);
      }
    } catch (error) {
      showLoadError(error);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    cacheNodes();
    syncThemeSwitch();
    nodes["theme-toggle"].addEventListener("click", toggleTheme);
    nodes["start-triage"].addEventListener("click", emitTriageRequest);
    loadAlerts();
  });
})();
