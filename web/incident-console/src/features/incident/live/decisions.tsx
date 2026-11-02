import { useT } from "@/i18n";
import type { Mitigation } from "@/lib/incident-api";
import type { LiveIncident } from "@/lib/live-incident";
import { usePlan } from "./proposal";
import { Prose, Stamp, useActorName, useSay } from "./say";
import { executionLine, type StoryEntry } from "./story";

export type Outcome = "approved" | "rejected" | "changes_requested";

export interface Decided {
  entry: StoryEntry;
  outcome: Outcome;
  /** It decided the proposal on record; an earlier one was replaced and its plan is gone. */
  current: boolean;
}

/**
 * Every decision on a proposal, oldest first, from the console, Telegram or the API alike: they
 * all send the same governed command. Rejecting and sending back share one event, so the current
 * proposal's approval status tells them apart.
 */
export function decisionsOf(live: LiveIncident, story: StoryEntry[]): Decided[] {
  const reasoning = typeof live.reasoning === "object" ? live.reasoning : null;
  const proposed = live.events.filter((event) => event.summary === "Mitigation proposed.").map((event) => Date.parse(event.occurred_at));
  const latest = Math.max(-Infinity, ...proposed);
  const decided = story.filter((entry) => /^event\.(approved|rejected)/.test(entry.line.key));
  return decided.map((entry, index) => {
    const current = index === decided.length - 1 && entry.at >= latest && Boolean(reasoning?.mitigation_strategy);
    const status = reasoning?.mitigation_strategy?.approval_status;
    const approved = entry.line.key.startsWith("event.approved");
    const outcome: Outcome = approved ? "approved" : current && status === "changes_requested" ? "changes_requested" : "rejected";
    return { entry, outcome, current };
  });
}

const TONE: Record<Outcome, string> = { approved: "text-[var(--ok)]", rejected: "text-foreground", changes_requested: "text-foreground" };

function Title({ mitigation }: { mitigation: Mitigation }) {
  return <Prose text={usePlan(mitigation).title} />;
}

/** What the approval ran, in words, with the receipt's id and duration in its technical detail. */
function Receipt({ mitigation }: { mitigation: Mitigation }) {
  const t = useT("incident");
  const say = useSay();
  const line = executionLine(mitigation);
  const ran = mitigation.execution;
  if (!line || !ran) return null;
  return (
    <>
      <p data-receipt="" className="mt-2 text-[var(--text-2)]">
        <Prose text={say(line)} />
      </p>
      <details className="mt-1 font-mono text-xs text-[var(--dim)]">
        <summary className="cursor-pointer text-[var(--mist)]">{t("receipt.technical")}</summary>
        <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
          <dt>{t("receipt.id")}</dt>
          <dd>{ran.execution_id}</dd>
          {ran.duration_ms !== undefined && <dt>{t("receipt.duration")}</dt>}
          {ran.duration_ms !== undefined && <dd>{`${(ran.duration_ms / 1000).toFixed(1)} s`}</dd>}
          {ran.replayed && <dt>{t("receipt.replayed")}</dt>}
          {ran.replayed && <dd>✓</dd>}
        </dl>
      </details>
    </>
  );
}

/** What was decided, by whom and when. Nothing here waits for anyone, so nothing is amber. */
export function Decisions({ decisions, mitigation }: { decisions: Decided[]; mitigation: Mitigation | null | undefined }) {
  const t = useT("incident");
  const name = useActorName();
  return (
    <section aria-label={t("decisions.label")} className="rounded-2xl border px-[30px] pt-6 pb-2">
      <h2 className="mb-2 font-mono text-[13px] font-medium text-[var(--mist)]">{t("decisions.label")}</h2>
      <ol className="list-none p-0">
        {decisions.map(({ entry, outcome, current }) => (
          <li key={entry.id} className="border-t py-4 first:border-t-0">
            <p className="mb-1.5 font-display text-[22px] leading-[1.15] [&_code]:text-[0.7em] [&_code]:font-normal">
              {current && mitigation ? <Title mitigation={mitigation} /> : t("decisions.earlier")}
            </p>
            <p className="font-mono text-[13px] text-[var(--dim)]">
              <span className={TONE[outcome]}>{t(`decision.${outcome}`)}</span> · {name(entry.actor)} ·{" "}
              <Stamp at={entry.at} />
            </p>
            {current && outcome === "approved" && mitigation && <Receipt mitigation={mitigation} />}
          </li>
        ))}
      </ol>
    </section>
  );
}
