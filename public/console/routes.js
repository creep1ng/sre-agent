// Canonical console routes. A view is addressed as /?view=<id>&<params>; parameters only select
// what to read (ADR-009, section 12). `legacy` marks surfaces that still open as their own page;
// `incident` marks views that read one incident and keep it in focus.
export const DOMAINS = Object.freeze({
  incidents: "Atención a incidentes",
  governance: "Gobierno de IA",
});

export const DEFAULT_VIEW = "alerts";

export const VIEWS = Object.freeze({
  alerts: {
    domain: "incidents",
    label: "Alertas",
    path: "/public/incident-ui/alerts.html",
    module: "/public/incident-ui/alerts.js",
    session: false,
  },
  triage: {
    domain: "incidents",
    label: "Triage",
    path: "/public/admin/triage.html",
    module: "/public/admin/triage.js",
  },
  "war-room": {
    domain: "incidents",
    label: "War room",
    path: "/public/incident-ui/war-room.html",
    module: "/public/incident-ui/war-room.js",
    incident: true,
  },
  decisions: {
    domain: "incidents",
    label: "Decisiones",
    path: "/public/incident-ui/review.html",
    module: "/public/incident-ui/review.js",
    incident: true,
  },
  postmortem: {
    domain: "incidents",
    label: "Postmortem",
    path: "/public/incident-ui/postmortem.html",
    module: "/public/incident-ui/postmortem.js",
    incident: true,
  },
  principals: {
    domain: "governance",
    label: "Principals",
    path: "/public/admin/principals.html",
    legacy: true,
  },
  resources: {
    domain: "governance",
    label: "Recursos y aliases",
    path: "/public/admin/model-aliases.html",
    legacy: true,
  },
  grants: {
    domain: "governance",
    label: "Grants",
    path: "/public/admin/grants.html",
    legacy: true,
  },
  audit: {
    domain: "governance",
    label: "Auditoría y consumo",
    path: "/public/admin/audit-events.html",
    legacy: true,
  },
  consumption: {
    domain: "governance",
    label: "Auditoría y consumo",
    nav: "audit",
    path: "/public/admin/consumption.html",
    legacy: true,
  },
});

const VIEW_BY_PATH = new Map(Object.entries(VIEWS).map(([id, view]) => [view.path, id]));

export function viewForPath(pathname) {
  return VIEW_BY_PATH.get(pathname) ?? null;
}

export function viewById(viewId) {
  return Object.hasOwn(VIEWS, viewId) ? VIEWS[viewId] : null;
}

// Builds the address of a view. Legacy surfaces keep their page until they move into the console.
export function hrefFor(viewId, params = {}) {
  const view = viewById(viewId);
  const query = new URLSearchParams();
  if (!view?.legacy) query.set("view", viewId);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const search = query.toString();
  const path = view?.legacy ? view.path : "/";
  return search ? `${path}?${search}` : path;
}

// Reads the route of a console address; unknown views stay unknown instead of falling back.
export function routeFrom(location) {
  const params = new URLSearchParams(location.search);
  const viewId = params.get("view") ?? DEFAULT_VIEW;
  params.delete("view");
  return { viewId, view: viewById(viewId), params };
}
