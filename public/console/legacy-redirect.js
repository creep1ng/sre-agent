// A surface that moved into the console keeps its old address: links and bookmarks to the page
// open the same view, with the same read parameters, inside the console.
(() => {
  const view = document.currentScript?.dataset.view;
  if (!view) return;
  const target = new URL("/", window.location.origin);
  target.searchParams.set("view", view);
  for (const [key, value] of new URLSearchParams(window.location.search)) {
    if (key !== "view") target.searchParams.append(key, value);
  }
  target.hash = window.location.hash;
  window.location.replace(target.href);
})();
