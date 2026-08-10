const root = document.documentElement;
const themeButtons = [...document.querySelectorAll("[data-theme-option]")];
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
const liveRegion = document.querySelector("#live-region");

function readThemePreference() {
  try {
    return localStorage.getItem("ma-theme") || "system";
  } catch (_) {
    return "system";
  }
}

function applyTheme(preference) {
  if (preference === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = preference;
  }

  themeButtons.forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.themeOption === preference),
    );
  });

  const resolvedTheme =
    preference === "system"
      ? systemTheme.matches
        ? "dark"
        : "light"
      : preference;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", resolvedTheme === "dark" ? "#0a0e1d" : "#fafaff");
}

themeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const preference = button.dataset.themeOption;
    try {
      localStorage.setItem("ma-theme", preference);
    } catch (_) {}
    applyTheme(preference);
    liveRegion.textContent = `${preference} theme selected`;
  });
});

systemTheme.addEventListener("change", () => {
  if (readThemePreference() === "system") applyTheme("system");
});

applyTheme(readThemePreference());

document.querySelectorAll('[role="tablist"]').forEach((tabList) => {
  const tabs = [...tabList.querySelectorAll('[role="tab"]')];

  function activateTab(tab) {
    tabs.forEach((candidate) => {
      const selected = candidate === tab;
      candidate.setAttribute("aria-selected", String(selected));
      candidate.tabIndex = selected ? 0 : -1;
      document.getElementById(candidate.getAttribute("aria-controls")).hidden =
        !selected;
    });
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
      event.preventDefault();
      let nextIndex = index;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft")
        nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    });
  });
});

document.querySelectorAll("[data-copy]").forEach((swatch) => {
  swatch.addEventListener("click", async () => {
    const value = swatch.dataset.copy;
    const label = swatch.querySelector(".swatch__value");
    const originalLabel = label.textContent;
    try {
      await navigator.clipboard.writeText(value);
      swatch.dataset.copied = "true";
      label.textContent = "Copied";
      liveRegion.textContent = `${value} copied to clipboard`;
      window.setTimeout(() => {
        delete swatch.dataset.copied;
        label.textContent = originalLabel;
      }, 1500);
    } catch (_) {
      liveRegion.textContent = `Copy unavailable. Value is ${value}`;
    }
  });
});

document.querySelectorAll("[data-dismiss]").forEach((button) => {
  button.addEventListener("click", () => {
    const alert = button.closest(".ma-alert");
    alert.hidden = true;
    liveRegion.textContent = "Notification dismissed";
  });
});

const auditRows = [...document.querySelectorAll("[data-audit-row]")];
document.querySelectorAll("[data-audit-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    const filter = button.dataset.auditFilter;
    document.querySelectorAll("[data-audit-filter]").forEach((candidate) => {
      candidate.setAttribute("aria-pressed", String(candidate === button));
      candidate.classList.toggle("ma-button--secondary", candidate === button);
      candidate.classList.toggle("ma-button--ghost", candidate !== button);
    });
    auditRows.forEach((row) => {
      row.hidden = filter !== "all" && row.dataset.decisionValue !== filter;
    });
    liveRegion.textContent = `Audit log filtered by ${filter}`;
  });
});

const navLinks = [...document.querySelectorAll(".catalog-nav a")];
const sections = navLinks
  .map((link) => document.querySelector(link.hash))
  .filter(Boolean);
const sectionObserver = new IntersectionObserver(
  (entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    navLinks.forEach((link) => {
      if (link.hash === `#${visible.target.id}`)
        link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  },
  { rootMargin: "-20% 0px -65% 0px", threshold: [0, 0.2, 0.5] },
);

sections.forEach((section) => sectionObserver.observe(section));
