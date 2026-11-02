import { ArrowUpRightIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Prose, useActorName, useSay, useWhen } from "./say";
import type { AgentStatus } from "./status";
import type { StoryEntry, Verdict } from "./story";
import { VerificationStep, type Verification } from "./verification";

/** Measured verdicts in their tone; context (memories, knowledge) in mist, never as a measure. */
export const VERDICT_TONE: Record<Verdict, string> = {
  supports: "text-[var(--ok)]",
  contradicts: "text-[var(--danger)]",
  inconclusive: "text-[var(--dim)]",
  empty: "text-[var(--dim)]",
  memory: "text-[var(--mist)] italic",
  knowledge: "text-[var(--mist)] italic",
};

const ROW = "grid scroll-mt-10 grid-cols-[72px_40px_minmax(0,1fr)] items-start sm:grid-cols-[92px_40px_minmax(0,1fr)]";
const TIME = "pt-[7px] pr-3.5 text-right font-mono text-[13px] font-medium text-[var(--mist)] tabular";

function Dot({ children, now }: { children?: ReactNode; now?: boolean }) {
  return (
    <span className="relative self-stretch before:absolute before:inset-y-0 before:left-1/2 before:-ml-px before:w-0.5 before:bg-[var(--mist-line)] group-first:before:top-3 group-last:before:bottom-auto group-last:before:h-3">
      <span
        className={cn(
          "relative mx-auto grid size-[26px] place-items-center rounded-full border border-[var(--mist)] bg-background font-mono text-[11px] font-medium text-[var(--mist)]",
          "group-target:bg-[var(--mist)] group-target:text-background",
          now && "border-star text-star-ink",
        )}
      >
        {children ?? <span className="size-1.5 rounded-full bg-current" />}
      </span>
    </span>
  );
}

function Step({ entry }: { entry: StoryEntry }) {
  const t = useT("incident");
  const say = useSay();
  const name = useActorName();
  const when = useWhen();
  const now = useNow();
  const author = entry.actor.kind === "system" ? entry.actor.name : undefined;
  return (
    <li id={entry.id} className={cn("group", ROW)}>
      <time className={TIME}>{when(entry.at, now)}</time>
      <Dot>{entry.number}</Dot>
      <div className="pt-0.5 pb-[30px] pl-1.5">
        <p className={cn("m-0 rounded-md group-target:bg-[var(--mist-wash)]", entry.tone === "critical" && "text-[var(--danger)]")}>
          {entry.actor.kind !== "system" && <b className="font-medium text-foreground">{name(entry.actor)} · </b>}
          <Prose text={say(entry.line)} />
          {author && <span className="text-[var(--dim)]"> · {t("change.by", { author })}</span>}
        </p>
        {entry.quote && (
          <p className="mt-1 text-[var(--text-2)]">
            <Prose text={entry.quote} />
          </p>
        )}
        {(entry.verdict || entry.link) && (
          <span className="mt-1.5 block font-mono text-[13px] leading-normal text-[var(--dim)]">
            {entry.verdict && <em className={cn("mr-2.5 not-italic", VERDICT_TONE[entry.verdict])}>{t(`verdict.${entry.verdict}`)}</em>}
            {entry.link?.external ? (
              <a href={entry.link.to} target="_blank" rel="noreferrer" className="text-[var(--mist)] hover:text-foreground">
                {t("card.open")} <ArrowUpRightIcon className="inline size-3" aria-hidden="true" />
              </a>
            ) : (
              entry.link && (
                <Link to={entry.link.to} className="text-[var(--mist)] hover:text-foreground">
                  {t("card.open")} <ArrowUpRightIcon className="inline size-3" aria-hidden="true" />
                </Link>
              )
            )}
          </span>
        )}
        {entry.query && (
          <details className="mt-1.5 font-mono text-xs text-[var(--dim)]">
            <summary className="cursor-pointer text-[var(--mist)]">{t(entry.query.label)}</summary>
            <pre className="mt-1 rounded-md bg-code p-2 whitespace-pre-wrap">
              {[entry.query.tool, entry.query.window].filter(Boolean).join(" · ")}
              {"\n"}
              {entry.query.text}
            </pre>
          </details>
        )}
      </div>
    </li>
  );
}

/** What is happening now closes the timeline: the agent at work, or amber when it waits for you. */
function Now({ status }: { status: AgentStatus }) {
  const t = useT("incident");
  const now = useNow();
  const when = useWhen();
  if (status.kind !== "working" && status.kind !== "waiting") return null;
  const waiting = status.kind === "waiting";
  return (
    <li data-decision={waiting ? "" : undefined} className={cn("group", ROW)}>
      <time className={cn(TIME, waiting && "text-star-ink")}>{waiting ? when(status.since, now) : formatClock(now - status.since)}</time>
      <Dot now={waiting}>→</Dot>
      <p className={cn("m-0 pt-0.5 pb-[30px] pl-1.5", waiting ? "text-star-ink" : "text-shimmer")}>
        {t(waiting ? "event.now.waiting" : "event.now.working")}
      </p>
    </li>
  );
}

export function Timeline({ story, status, verification }: { story: StoryEntry[]; status: AgentStatus; verification: Verification | null }) {
  const t = useT("incident");
  // The verification step folds in the check it reports and sits where its outcome became known.
  const steps = story.filter((entry) => entry.id !== verification?.check?.id);
  const split = verification ? steps.filter((entry) => entry.at <= verification.at).length : steps.length;
  return (
    <ol aria-label={t("timeline")} className="mb-14 list-none p-0">
      {steps.slice(0, split).map((entry) => (
        <Step key={entry.id} entry={entry} />
      ))}
      {verification && <VerificationStep verification={verification} row={ROW} time={TIME} />}
      {steps.slice(split).map((entry) => (
        <Step key={entry.id} entry={entry} />
      ))}
      <Now status={status} />
    </ol>
  );
}
