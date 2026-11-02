import { useEffect, useSyncExternalStore } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

/** "system" follows prefers-color-scheme; "light" and "dark" are overrides stored per browser. */
export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_PREFERENCES: readonly ThemePreference[] = ["system", "light", "dark"];

export const useTheme = create<{ theme: ThemePreference; setTheme: (theme: ThemePreference) => void }>()(
  persist(
    (set) => ({
      theme: "system",
      setTheme: (theme) => set({ theme }),
    }),
    { name: "midnight-theme" },
  ),
);

const DARK_QUERY = "(prefers-color-scheme: dark)";

function systemTheme(): ResolvedTheme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

function subscribeSystem(onChange: () => void) {
  const media = window.matchMedia(DARK_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function resolve(theme: ThemePreference): ResolvedTheme {
  return theme === "system" ? systemTheme() : theme;
}

/** html.dark keeps the night tokens; without it src/index.css reassigns them to the light theme. */
function apply(resolved: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", resolved === "dark");
  document.documentElement.style.colorScheme = resolved;
}

// Before the first render, so a stored override does not flash the other theme.
if (typeof window !== "undefined") apply(resolve(useTheme.getState().theme));

/** The theme on screen, re-rendering when the preference or the OS setting changes. */
export function useResolvedTheme(): ResolvedTheme {
  const theme = useTheme((state) => state.theme);
  const system = useSyncExternalStore(subscribeSystem, systemTheme, () => "dark" as const);
  return theme === "system" ? system : theme;
}

/** Keeps the <html> classes in sync with the preference and the OS setting. Mount once. */
export function useApplyTheme() {
  const resolved = useResolvedTheme();
  useEffect(() => apply(resolved), [resolved]);
}
