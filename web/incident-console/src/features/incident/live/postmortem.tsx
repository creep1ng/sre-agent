import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import type { Cited, Postmortem as PostmortemRecord } from "@/lib/incident-api";
import type { LiveIncident } from "@/lib/live-incident";
import { useIncidentTitle } from "@/lib/title";
import { cn } from "@/lib/utils";
import { Prose, Stamp, useActorName, useSay } from "./say";
import { Statement } from "./statement";
import { executionLine, type Key, type StoryEntry } from "./story";
import type { DecisionError } from "./use-decision";
import { span } from "./verification";

/** One section: its paragraphs as recorded, or what else it shows. */
function Section({ title, texts = [], children }: { title: string; texts?: string[]; children?: ReactNode }) {
  return (
    <section className="mt-7 first:mt-0">
      <h3 className="mb-2 font-mono text-[13px] font-medium text-[var(--mist)]">{title}</h3>
      <div className="max-w-[72ch] text-[var(--text-2)] [&_p+p]:mt-2">
        {texts.map((text, index) => (
          <p key={index}>
            <Prose text={text} />
          </p>
        ))}
        {children}
      </div>
    </section>
  );
}

/** The agent's own steps the story tells elsewhere (the plan, the work), worded here. */
const AGENT_STEPS: Record<string, Key> = { "Mitigation proposed.": "event.mitigation", "Investigation started.": "event.working" };

/**
 * A cited moment told as the timeline tells its event, at the event's local time; ids never show.
 * What the story leaves out (the agent continuing within its run) is left out here too.
 */
function Moment({ item, live, story }: { item: Cited; live: LiveIncident; story: StoryEntry[] }) {
  const t = useT("incident");
  const say = useSay();
  const name = useActorName();
  const event = live.events.find((candidate) => candidate.event_id === item.event_id);
  const entry = story.find((candidate) => candidate.id === `step-${item.event_id}`);
  if (!entry && !AGENT_STEPS[item.description]) return null;
  return (
    <li className="grid grid-cols-[64px_minmax(0,1fr)] gap-x-3 py-1">
      {event ? <Stamp at={Date.parse(event.occurred_at)} className="font-mono text-[13px] text-[var(--mist)] tabular-nums" /> : <span />}
      <span>
        {entry ? (
          <>
            {entry.actor.kind !== "system" && `${name(entry.actor)} · `}
            <Prose text={say(entry.line)} />
          </>
        ) : (
          `${t("actor.agent")} · ${t(AGENT_STEPS[item.description])}`
        )}
      </span>
    </li>
  );
}

interface PostmortemProps {
  live: LiveIncident;
  story: StoryEntry[];
  sending: boolean;
  error: DecisionError | null;
  canDecide: boolean;
  onClose: (version: number, approved: boolean) => void;
}

/**
 * The agent's draft, read-only, in narrative sections (#711). While the incident is in its
 * postmortem, «Aprobar y cerrar» is the decision pending and the only amber here.
 */
export function PostmortemDraft({ live, story, sending, error, canDecide, onClose }: PostmortemProps) {
  const t = useT("incident");
  const title = useIncidentTitle();
  const say = useSay();
  const record = live.postmortem;
  const state = live.detail?.state;
  const content = typeof record === "object" ? record?.content : undefined;
  const mitigation = typeof live.reasoning === "object" ? live.reasoning?.mitigation_strategy : null;
  const ran = executionLine(mitigation);
  const open = state === "postmortem" && content !== undefined;
  // The agent that opened the postmortem wrote the model's draft; `system` wrote the record's; a person, neither.
  const opener = live.events.find((event) => event.summary === "Postmortem started." && event.actor.type === "agent")?.actor.reference?.principal_id;
  const author = typeof record === "object" && record?.version === 1 ? record.updated_by : undefined;
  const draft = author === "system" ? "record" : author && author === opener ? "agent" : null;
  const approved = (pm: PostmortemRecord) => pm.review.status === "approved" && pm.review.reviewed_version === pm.version;
  return (
    <section aria-label={t("postmortem.label")} className="mb-14 rounded-2xl border px-[30px] py-7">
      <h2 className="mb-1.5 font-display text-[30px] leading-[1.1] tracking-[-0.01em]">{t("postmortem.label")}</h2>
      <p data-title={live.detail?.title ? "agent" : "alert"} className="mb-6 font-display text-xl leading-snug text-[var(--text-2)]">
        {title(live.detail)}
      </p>
      {/* Which first draft this is: the model's, or the one composed from the record when the model failed (#711). */}
      {content && draft && (
        <p data-draft={draft} className="-mt-4 mb-6 font-mono text-[13px] text-[var(--dim)]">
          {t(draft === "record" ? "postmortem.byRecord" : "postmortem.byAgent")}
        </p>
      )}
      {record === "forbidden" || (record && !record.content_included) ? (
        <p className="text-[var(--dim)]">{t("postmortem.restricted")}</p>
      ) : !content ? (
        <p className="text-shimmer">{t("postmortem.drafting")}</p>
      ) : (
        <>
          <Section title={t("postmortem.happened")} texts={[content.summary, content.impact]} />
          <Section title={t("postmortem.cause")}>
            <Statement statement={content.cause.statement} />
          </Section>
          <Section title={t("postmortem.did")} texts={[content.strategy, ...(ran ? [say(ran)] : [])]} />
          <Section title={t("postmortem.verified")} texts={[content.verification]} />
          <Section title={t("postmortem.timeline")}>
            <ol aria-label={t("postmortem.timeline")} className="list-none p-0">
              {content.timeline.map((item) => (
                <Moment key={item.event_id} item={item} live={live} story={story} />
              ))}
            </ol>
          </Section>
          {content.unknowns.length + content.pending.length > 0 && (
            <Section title={t("postmortem.unknowns")} texts={[...content.unknowns, ...content.pending]} />
          )}
        </>
      )}
      {open && typeof record === "object" && record && (
        <div data-decision="" className="-mx-[30px] mt-8 -mb-7 flex flex-wrap items-center justify-end gap-2.5 rounded-b-2xl border-t border-star bg-[color-mix(in_oklab,var(--star)_8%,transparent)] px-[18px] py-4">
          {error && (
            <span role="alert" className="mr-auto text-sm text-[var(--danger)]">
              {t(`close.${error}`)}
            </span>
          )}
          <Button size="lg" className="bg-star font-mono text-on-star hover:bg-star/90" disabled={!canDecide || sending} onClick={() => onClose(record.version, approved(record))}>
            {t("postmortem.close")}
          </Button>
        </div>
      )}
    </section>
  );
}

const MILESTONES = ["detected", "declared", "mitigated", "recovered", "closed"] as const;

/** When each milestone happened, from the alert and the incident's events; undefined if it never did. */
function milestones(live: LiveIncident): Partial<Record<(typeof MILESTONES)[number], number>> {
  const at = (match: (summary: string) => boolean) => {
    const event = live.events.findLast((candidate) => match(candidate.summary));
    return event ? Date.parse(event.occurred_at) : undefined;
  };
  const first = live.events.map((event) => Date.parse(event.occurred_at)).sort((a, b) => a - b)[0];
  const declared = at((summary) => summary === "Incident declared.") ?? first;
  const observed = Date.parse(live.detail?.alert?.observed_at ?? "");
  return {
    detected: Number.isFinite(observed) ? Math.min(observed, declared ?? observed) : declared,
    declared,
    mitigated: at((summary) => summary.startsWith("Mitigation approved")),
    recovered: at((summary) => summary === "Service verified stable."),
    closed: at((summary) => summary === "Incident closed."),
  };
}

/** A closed incident's summary: its milestones in order, each with how long after detection. */
export function ClosingSummary({ live }: { live: LiveIncident }) {
  const t = useT("incident");
  const title = useIncidentTitle();
  const times = milestones(live);
  const start = times.detected;
  return (
    <section aria-label={t("closing.label")} className="mb-12">
      <h2 className="mb-1 font-display text-[26px] leading-[1.1] tracking-[-0.01em]">{t("closing.label")}</h2>
      <p data-title={live.detail?.title ? "agent" : "alert"} className="mb-4 text-[var(--text-2)]">
        {title(live.detail)}
      </p>
      <ol aria-label={t("closing.label")} className="grid list-none gap-y-2 p-0 sm:grid-cols-5 sm:gap-x-4">
        {MILESTONES.map((milestone) => {
          const at = times[milestone];
          return (
            <li key={milestone} data-milestone={milestone} className={cn("border-t pt-2", at === undefined && "text-[var(--dim)]")}>
              <span className="block font-mono text-[13px] text-[var(--mist)]">{t(`closing.${milestone}`)}</span>
              {at !== undefined && <Stamp at={at} className="block w-fit text-lg tabular-nums" />}
              {at !== undefined && start !== undefined && milestone !== "detected" && (
                <span className="block text-xs text-[var(--dim)]">{t("closing.after", { after: span(at - start) })}</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
