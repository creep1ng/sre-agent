import { hrefFor } from "./routes.js";

// The incident in focus. The band above the incident views shows the incident that the mounted
// view read from the API (it never reads on its own) and a journey that keeps that incident and run.
const JOURNEY = Object.freeze(["alerts", "triage", "war-room", "decisions", "postmortem"]);
const STEP_LABELS = Object.freeze({
  alerts: "Alerta",
  triage: "Triage",
  "war-room": "War room",
  decisions: "Decisión",
  postmortem: "Postmortem",
});

// Journey step of each state of workflow 1.0.0 (agent/workflows/incident-response.yaml): detection,
// triage, war room and investigation, mitigation decision and verification, postmortem and closure.
// Only triage_declare reaches `active`, so an incident past triage was declared there.
const STEP_BY_STATE = Object.freeze({
  "1.0.0": Object.freeze({
    detected: 0,
    triage: 1,
    dismissed: 1,
    linked: 1,
    active: 2,
    investigating: 2,
    mitigating: 3,
    verifying: 3,
    resolved: 3,
    postmortem: 4,
    closed: 4,
  }),
});

const STATE_LABELS = Object.freeze({
  detected: "Detectado",
  triage: "En triage",
  dismissed: "Descartado",
  linked: "Vinculado",
  active: "Activo",
  investigating: "Investigando",
  mitigating: "Mitigando",
  verifying: "Verificando",
  resolved: "Resuelto",
  postmortem: "En postmortem",
  closed: "Cerrado",
});

const RUN_LABELS = Object.freeze({
  running: "Run en curso",
  awaiting_human: "Decisión pendiente",
  completed: "Run completado",
  terminated: "Run terminado",
});

const SEVERITY_TONES = Object.freeze({ sev1: "critical", sev2: "warning", sev3: "info", sev4: "info" });
const PROGRESS_LABELS = Object.freeze({ done: "completado", current: "etapa actual", pending: "pendiente" });
const SVG = "http://www.w3.org/2000/svg";

const text = (value) => (typeof value === "string" && value !== "" ? value : null);
const stateLabel = (state) => STATE_LABELS[state] ?? text(state) ?? "—";

function formatTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return text(value) ?? "—";
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short", hour12: false }).format(parsed);
}

function runsOf(detail) {
  return (Array.isArray(detail.runs) ? detail.runs : []).filter((run) => typeof run?.run_id === "string");
}

// What each step says about this incident, from the read alone.
function stepDetail(stepView, { detail, run, step }) {
  switch (stepView) {
    case "alerts":
      return text(detail.alert?.alert_id) ?? "Sin alerta";
    case "triage":
      if (step === null) return "—";
      return step > 1 ? "Declarado" : step === 1 ? stateLabel(detail.state) : "Pendiente";
    case "war-room":
      return stateLabel(detail.state);
    case "decisions":
      if (!run) return "Sin run";
      if (step === null) return RUN_LABELS[run.status] ?? "—";
      if (run.status === "awaiting_human" && step === 3) return RUN_LABELS.awaiting_human;
      return step < 3 ? "Pendiente" : step === 3 ? stateLabel(detail.state) : "Completada";
    default:
      if (step === null) return "—";
      return step < 4 ? "Pendiente" : stateLabel(detail.state);
  }
}

function stepTarget(stepView, { detail, run }) {
  const focus = { incident_id: detail.incident_id, run_id: run?.run_id };
  switch (stepView) {
    case "alerts":
      return hrefFor("alerts");
    case "triage": {
      const alertId = text(detail.alert?.alert_id);
      return alertId ? hrefFor("triage", { alert_id: alertId }) : null;
    }
    case "decisions":
      return run ? hrefFor("decisions", focus) : null;
    default:
      return hrefFor(stepView, focus);
  }
}

function marker(index, progress) {
  const node = document.createElement("span");
  node.className = "console-journey__marker";
  node.setAttribute("aria-hidden", "true");
  if (progress === "done") {
    const icon = document.createElementNS(SVG, "svg");
    icon.setAttribute("class", "ma-icon");
    const use = document.createElementNS(SVG, "use");
    use.setAttribute("href", "/public/icons.svg#icon-check");
    icon.append(use);
    node.append(icon);
  } else {
    node.textContent = String(index + 1);
  }
  return node;
}

export function createIncidentFocus(root) {
  const byId = (id) => document.getElementById(id);
  const fields = {
    severity: byId("incident-focus-severity"),
    state: byId("incident-focus-state"),
    title: byId("incident-focus-title"),
    incident: byId("incident-focus-incident"),
    run: byId("incident-focus-run"),
    version: byId("incident-focus-version"),
    updated: byId("incident-focus-updated"),
    journey: byId("incident-focus-journey"),
  };
  let viewId = null;
  let routed = null; // incident and run addressed by the current incident route
  let read = null; // incident and run the mounted view read and still holds
  let recent = null; // last incident read in this session, kept for the navigation

  function renderJourney(detail, run) {
    const step = STEP_BY_STATE[detail.workflow_version]?.[detail.state] ?? null;
    fields.journey.replaceChildren(
      ...JOURNEY.map((stepView, index) => {
        const target = stepTarget(stepView, { detail, run });
        const node = document.createElement(target ? "a" : "span");
        node.className = "console-journey__step";
        if (target) node.href = target;
        else node.setAttribute("aria-disabled", "true");
        if (stepView === viewId) node.setAttribute("aria-current", "page");
        const progress = step === null ? null : index < step ? "done" : index === step ? "current" : "pending";
        if (progress) node.dataset.progress = progress;
        const label = document.createElement("span");
        label.className = "console-journey__label";
        label.textContent = STEP_LABELS[stepView];
        const detailNode = document.createElement("span");
        detailNode.className = "console-journey__detail";
        detailNode.textContent = stepDetail(stepView, { detail, run, step });
        detailNode.title = detailNode.textContent;
        node.append(marker(index, progress), label, detailNode);
        if (progress) {
          const status = document.createElement("span");
          status.className = "ma-sr-only";
          status.textContent = ` (${PROGRESS_LABELS[progress]})`;
          node.append(status);
        }
        const item = document.createElement("li");
        item.append(node);
        return item;
      }),
    );
  }

  // Without a read the band holds nothing: no title, identifiers or journey of an earlier incident.
  function render() {
    root.hidden = read === null;
    if (read === null) {
      for (const [name, node] of Object.entries(fields)) {
        if (name === "journey") node.replaceChildren();
        else node.textContent = "";
      }
      return;
    }
    const { detail, run } = read;
    const severity = text(detail.severity);
    root.dataset.tone = SEVERITY_TONES[severity] ?? "info";
    fields.severity.textContent = severity ?? "sin severidad";
    fields.severity.dataset.tone = SEVERITY_TONES[severity] ?? "info";
    fields.state.textContent = stateLabel(detail.state);
    fields.state.dataset.tone = "info";
    fields.title.textContent = text(detail.alert?.summary) ?? `Incidente ${detail.incident_id}`;
    fields.incident.textContent = detail.incident_id;
    fields.run.textContent = run?.run_id ?? "Sin run";
    fields.version.textContent = Number.isSafeInteger(detail.version) ? String(detail.version) : "—";
    fields.updated.textContent = formatTimestamp(detail.updated_at);
    renderJourney(detail, run);
  }

  return Object.freeze({
    // Every console render: the route decides which incident may be in focus.
    route(nextViewId, view, params) {
      viewId = nextViewId;
      const incidentId = view?.incident ? text(params.get("incident_id")) : null;
      routed = incidentId ? { incident_id: incidentId, run_id: text(params.get("run_id")) } : null;
      if (read && read.detail.incident_id !== routed?.incident_id) read = null;
      render();
    },
    // From the mounted view: the incident it read, or null when it holds none (error or no session).
    show(fromViewId, detail, runId) {
      if (fromViewId !== viewId) return;
      if (detail === null || detail === undefined) {
        read = null;
      } else {
        if (!routed || detail.incident_id !== routed.incident_id) return;
        const runs = runsOf(detail);
        const run =
          runs.find((entry) => entry.run_id === runId) ??
          runs.find((entry) => entry.run_id === routed.run_id) ??
          runs.at(-1) ??
          null;
        read = { detail, run };
        recent = { incident_id: detail.incident_id, run_id: run?.run_id };
      }
      render();
    },
    // A session that ends takes the incident with it.
    clear() {
      read = null;
      recent = null;
      render();
    },
    // Where the navigation opens an incident view: the incident on screen, else the last one read.
    get params() {
      if (read) return { incident_id: read.detail.incident_id, run_id: read.run?.run_id };
      return routed ?? recent ?? {};
    },
  });
}
