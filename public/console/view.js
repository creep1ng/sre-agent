// Hosts one surface at a time inside the console. A surface keeps its markup in its own page
// (the <main> element) and its behavior in its module; every mount evaluates a fresh module
// instance, so module-level state never leaks between visits.
let mounting = null;
let sequence = 0;
const templates = new Map();

// Called by a view module while it evaluates. Outside a console mount there is no context.
export function mountedView() {
  if (!mounting) throw new Error("This view must be opened from the midnight.agent console.");
  return mounting;
}

function templateFor(path) {
  if (!templates.has(path)) {
    const pending = fetch(path, { credentials: "omit" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}.`);
        const page = new DOMParser().parseFromString(await response.text(), "text/html");
        const main = page.querySelector("main");
        if (!main) throw new Error(`${path} has no main element.`);
        return main;
      })
      .catch((error) => {
        templates.delete(path);
        throw error;
      });
    templates.set(path, pending);
  }
  return templates.get(path);
}

// The page's <main> becomes a region of the console's single main landmark.
function regionFrom(template, viewId) {
  const region = document.createElement("section");
  for (const { name, value } of template.attributes) region.setAttribute(name, value);
  region.append(...document.importNode(template, true).childNodes);
  region.dataset.consoleView = viewId;
  return region;
}

export async function mountView({ host, viewId, view, params, session, navigate, replaceParams, focusIncident }) {
  const template = await templateFor(view.path);
  const controller = new AbortController();
  const { signal } = controller;
  const root = regionFrom(template, viewId);
  host.replaceChildren(root);

  mounting = Object.freeze({
    id: viewId,
    root,
    signal,
    params: new URLSearchParams(params),
    client: session.client,
    get session() {
      return session.state;
    },
    // Runs now and on every session change until the view unmounts (ADR-009, section 11).
    onSession(listener) {
      const unsubscribe = session.subscribe(listener);
      signal.addEventListener("abort", unsubscribe, { once: true });
      listener(session.state);
    },
    navigate(target, targetParams = {}, options = {}) {
      if (!signal.aborted) navigate(target, targetParams, options);
    },
    replaceParams(next) {
      if (!signal.aborted) replaceParams(next);
    },
    // Shows the incident this view read in the console's focus band; null when it holds none.
    focusIncident(detail, runId = null) {
      if (!signal.aborted) focusIncident(viewId, detail, runId);
    },
  });
  sequence += 1;
  try {
    await import(`${view.module}?mount=${sequence}`);
  } catch (error) {
    controller.abort();
    throw error;
  } finally {
    mounting = null;
  }
  return Object.freeze({ root, unmount: () => controller.abort() });
}
