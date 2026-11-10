const KEY = "midnight-console-mode";

export type AppMode = "live" | "mock";

/**
 * Live is the production default. In a build with CONSOLE_SIMULATOR=1, `?mock`
 * opts the tab into the in-browser simulator; the flag lives in sessionStorage
 * and the query is removed so the address bar does not keep a non-production
 * hint. Without the variable the console is always live and `?mock` does nothing.
 */
function resolveMode(): AppMode {
  const url = new URL(window.location.href);
  if (url.searchParams.has("mock")) {
    try {
      sessionStorage.setItem(KEY, "mock");
    } catch {
      // Storage may be unavailable; the current page still runs in mock mode.
    }
    url.searchParams.delete("mock");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    return "mock";
  }
  try {
    return sessionStorage.getItem(KEY) === "mock" ? "mock" : "live";
  } catch {
    return "live";
  }
}

export const appMode: AppMode = __CONSOLE_SIMULATOR__ ? resolveMode() : "live";
