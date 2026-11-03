import { useCallback } from "react";
import { LOCALES, useLanguage, useT } from "@/i18n";

/*
 * An incident's title from the alert that opened it. A Grafana summary carries the rule's text
 * and then where its evidence lives, for the agent (demo/grafana/alerting/midnight.yaml); the
 * title keeps the rule's text only, worded in the console's language for the demo's two rules.
 * Telegram words its messages with the same rules (src/sre_agent/chat/outbox.py).
 */

const ERRORS = /^(\S+?):\s*([\d.]+)\s*% of spans failed over the last .+?\(threshold ([\d.]+)\s*%\)/i;
const LATENCY = /^(\S+?):\s*p95 of server spans is ([\d.]+)\s*ms over the last .+?\(threshold ([\d.]+)\s*ms\)/i;

/** The first sentence of an alert summary: the rule's text before where its evidence lives. */
export function firstSentence(text: string): string {
  const sentence = /^(.+?[.!?])(\s|$)/.exec(text)?.[1] ?? text;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

/** Words a title from an alert summary; null without one. */
export function useTitle() {
  const t = useT("incident");
  const locale = LOCALES[useLanguage((state) => state.language)];
  return useCallback(
    (summary: string | null | undefined): string | null => {
      if (!summary) return null;
      const number = (value: string) => new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Number(value));
      const errors = ERRORS.exec(summary);
      if (errors) return t("title.errors", { service: errors[1], value: number(errors[2]), threshold: number(errors[3]) });
      const latency = LATENCY.exec(summary);
      if (latency) return t("title.latency", { service: latency[1], value: number(latency[2]), threshold: number(latency[3]) });
      return firstSentence(summary).replace(/\.$/, "");
    },
    [t, locale],
  );
}
