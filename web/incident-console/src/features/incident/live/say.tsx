import { Fragment, useCallback } from "react";
import { LOCALES, useLanguage, useT } from "@/i18n";
import type { Actor, Line } from "./story";

/** Words a story line in the current language, params included. */
export function useSay() {
  const t = useT("incident");
  const say = useCallback(
    (line: Line): string =>
      t(line.key, Object.fromEntries(Object.entries(line.params ?? {}).map(([name, value]) => [name, typeof value === "string" ? value : say(value)]))),
    [t],
  );
  return say;
}

export function useActorName() {
  const t = useT("incident");
  return (actor: Actor) => (actor.kind === "person" ? (actor.name ?? t("actor.person")) : t(`actor.${actor.kind}`));
}

/** Text with `identifiers` in backticks, rendered as code. */
export function Prose({ text }: { text: string }) {
  return text.split(/`([^`]+)`/).map((part, index) => (index % 2 ? <code key={index}>{part}</code> : <Fragment key={index}>{part}</Fragment>));
}

/** "02:31" today, "vie 19:12" this week, "12 sep" before. */
export function useWhen() {
  const locale = LOCALES[useLanguage((state) => state.language)];
  return useCallback(
    (ms: number, now: number) => {
      const time = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(ms);
      const day = new Date(ms).toDateString() === new Date(now).toDateString();
      if (day) return time;
      if (now - ms < 6 * 24 * 3_600_000) return `${new Intl.DateTimeFormat(locale, { weekday: "short" }).format(ms).replace(".", "")} ${time}`;
      return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(ms).replace(".", "");
    },
    [locale],
  );
}
