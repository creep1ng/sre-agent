import { useCallback } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Language = "es" | "en";

export const LANGUAGES: readonly Language[] = ["es", "en"];

/** BCP 47 locale for Intl formatters in each language. */
export const LOCALES: Record<Language, string> = { es: "es-CO", en: "en-US" };

/**
 * One entry per feature namespace. Each Spanish catalog (src/i18n/es/<namespace>.ts) adds its own
 * entry with `declare module "@/i18n"`, so features add namespaces without editing this file.
 */
export interface Namespaces {}

/** The English catalog of a namespace: the same keys as the Spanish one, every one translated. */
export type Messages<Spanish> = { [Key in keyof Spanish]: string };

type Catalog = Record<string, string>;

// Every src/i18n/<language>/<namespace>.ts is bundled and registered by its path.
const catalogs: Record<Language, Record<string, Catalog>> = { es: {}, en: {} };
for (const [path, module] of Object.entries(import.meta.glob<Catalog>("./*/*.ts", { eager: true, import: "default" }))) {
  const [, language, namespace] = /^\.\/(es|en)\/(.+)\.ts$/.exec(path) ?? [];
  if (language) catalogs[language as Language][namespace] = module;
}

function browserLanguage(): Language {
  return typeof navigator !== "undefined" && navigator.language.toLowerCase().startsWith("en") ? "en" : "es";
}

/** The stored choice wins; without one, English browsers get English and everyone else Spanish. */
export const useLanguage = create<{ language: Language; setLanguage: (language: Language) => void }>()(
  persist(
    (set) => ({
      language: browserLanguage(),
      setLanguage: (language) => set({ language }),
    }),
    { name: "midnight-language" },
  ),
);

if (typeof document !== "undefined") {
  document.documentElement.lang = useLanguage.getState().language;
  useLanguage.subscribe(({ language }) => (document.documentElement.lang = language));
}

export type Params = Record<string, string | number>;

/** The message of `key` in the current language, with `{name}` placeholders filled from `params`. */
export function useT<Namespace extends keyof Namespaces>(namespace: Namespace) {
  const language = useLanguage((state) => state.language);
  return useCallback(
    (key: keyof Namespaces[Namespace] & string, params?: Params) => {
      const message = catalogs[language][namespace]?.[key] ?? catalogs.es[namespace]?.[key] ?? key;
      return message.replace(/\{(\w+)\}/g, (match, name: string) => (params && name in params ? String(params[name]) : match));
    },
    [language, namespace],
  );
}
