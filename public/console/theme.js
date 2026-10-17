// Applies the saved theme before the first paint and wires every Light/Auto/Dark control.
// The console and the design-system catalog share the "ma-theme" preference.
(() => {
  const KEY = "ma-theme";
  const CHOICES = ["light", "system", "dark"];
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const root = document.documentElement;

  function saved() {
    try {
      const value = window.localStorage.getItem(KEY);
      return CHOICES.includes(value) ? value : "system";
    } catch {
      return "system";
    }
  }

  function apply(choice) {
    root.dataset.themeChoice = choice;
    root.dataset.theme = choice === "system" ? (media.matches ? "dark" : "light") : choice;
    for (const button of document.querySelectorAll("[data-theme-option]")) {
      button.setAttribute("aria-pressed", String(button.dataset.themeOption === choice));
    }
  }

  apply(saved());
  media.addEventListener("change", () => {
    if (root.dataset.themeChoice === "system") apply("system");
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-theme-option]");
    if (!button || !CHOICES.includes(button.dataset.themeOption)) return;
    try {
      window.localStorage.setItem(KEY, button.dataset.themeOption);
    } catch {
      // The choice still applies to this document when storage is unavailable.
    }
    apply(button.dataset.themeOption);
  });

  document.addEventListener("DOMContentLoaded", () => apply(root.dataset.themeChoice));
})();
