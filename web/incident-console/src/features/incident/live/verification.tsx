import { CheckIcon, XIcon } from "lucide-react";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import type { LiveIncident } from "@/lib/live-incident";
import { cn } from "@/lib/utils";
import { Prose, useActorName, useSay, useWhen } from "./say";
import type { StoryEntry } from "./story";

/**
 * The failing signal measured again by the agent's verification (#723): the query, the alert
 * threshold and the points before and after the mitigation. Nothing stores it yet, so nothing
 * draws it; when #723 records it as evidence, `verificationOf` reads it into `series`.
 */
export interface SignalSeries {
  query: string;
  threshold?: number;
  /** [epoch ms, value], oldest first. */
  points: [number, number][];
}

export interface Verification {
  /** Where the step sits in the story: when the outcome became known, else right after the approval. */
  at: number;
  outcome: "passed" | "failed" | "waiting";
  approvedAt: number;
  /** When Grafana's resolution of the incident's alerts came in; undefined while any still fires. */
  resolvedAt?: number;
  firing: boolean;
  /** The recorded `verification_passed` or `verification_failed`, folded into this step. */
  check?: StoryEntry;
  series?: SignalSeries;
}

/** Whether the approved mitigation cleared the signal: the verification on record, else the alert's own resolution. */
export function verificationOf(live: LiveIncident, story: StoryEntry[]): Verification | null {
  const approval = story.findLast((entry) => entry.line.key.startsWith("event.approved"));
  if (!approval) return null;
  const check = story.find((entry) => entry.at >= approval.at && /^event\.(verified|verifyFailed)$/.test(entry.line.key));
  const firing = (live.alerts?.firing.length ?? 0) > 0;
  const resolutions = (live.alerts?.resolved ?? []).map((alert) => Date.parse(alert.origin?.observed_at ?? "")).filter(Number.isFinite);
  const resolvedAt = !firing && resolutions.length ? Math.max(...resolutions) : undefined;
  const outcome = check ? (check.line.key === "event.verified" ? "passed" : "failed") : resolvedAt ? "passed" : "waiting";
  const at = Math.max(approval.at + 1, check?.at ?? 0, resolvedAt ?? 0);
  // Intake records the resolution to the second: a resolution in the approval's own second is not before it.
  const approvedAt = Math.floor(approval.at / 1000) * 1000;
  return { at, outcome, approvedAt, resolvedAt, firing, check };
}

/** "95 s", "4 min", "2 h": how long the signal took to recover. */
function span(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 120) return `${seconds} s`;
  if (seconds < 7200) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

/** The stored series with the approval and the threshold marked (#927); drawn only from real points. */
export function SignalChart({ series, approvedAt }: { series: SignalSeries; approvedAt: number }) {
  const t = useT("incident");
  const times = series.points.map(([time]) => time);
  const values = [...series.points.map(([, value]) => value), series.threshold ?? 0];
  const [x0, x1] = [Math.min(...times, approvedAt), Math.max(...times, approvedAt)];
  const top = Math.max(...values) || 1;
  const x = (time: number) => ((time - x0) / (x1 - x0 || 1)) * 300;
  const y = (value: number) => 80 - (value / top) * 76;
  return (
    <svg viewBox="0 0 300 84" role="img" aria-label={t("verification.chart", { query: series.query })} className="mt-2 h-24 w-full max-w-md text-[var(--mist)]">
      {series.threshold !== undefined && (
        <line x1="0" x2="300" y1={y(series.threshold)} y2={y(series.threshold)} stroke="var(--danger)" strokeDasharray="4 3" />
      )}
      <line x1={x(approvedAt)} x2={x(approvedAt)} y1="0" y2="84" stroke="currentColor" strokeDasharray="2 2" />
      <polyline fill="none" stroke="var(--foreground)" strokeWidth="1.5" points={series.points.map(([time, value]) => `${x(time)},${y(value)}`).join(" ")} />
    </svg>
  );
}

const TONE = { passed: "text-[var(--ok)]", failed: "text-[var(--danger)]", waiting: "text-[var(--dim)]" } as const;

/** The step after the decision: whether the mitigation cleared the failing signal, and when. */
export function VerificationStep({ verification, row, time }: { verification: Verification; row: string; time: string }) {
  const t = useT("incident");
  const say = useSay();
  const name = useActorName();
  const when = useWhen();
  const now = useNow();
  const { outcome, resolvedAt, approvedAt, check, firing, series } = verification;
  const shown = check?.at ?? resolvedAt;
  const signal = resolvedAt
    ? t(resolvedAt >= approvedAt ? "verification.resolved" : "verification.resolvedBefore", { time: when(resolvedAt, now), after: span(resolvedAt - approvedAt) })
    : firing
      ? t("verification.firing")
      : !check && t("verification.waiting.text");
  return (
    <li id="step-verification" className={cn("group", row)}>
      <time className={time}>{shown ? when(shown, now) : ""}</time>
      <span className="relative self-stretch before:absolute before:inset-y-0 before:left-1/2 before:-ml-px before:w-0.5 before:bg-[var(--mist-line)] group-last:before:bottom-auto group-last:before:h-3">
        <span className={cn("relative mx-auto grid size-[26px] place-items-center rounded-full border border-current bg-background", TONE[outcome])}>
          {outcome === "passed" ? <CheckIcon className="size-3.5" /> : outcome === "failed" ? <XIcon className="size-3.5" /> : <span className="size-1.5 rounded-full bg-current" />}
        </span>
      </span>
      <div className="pt-0.5 pb-[30px] pl-1.5">
        <p className="m-0">
          <b className="font-medium text-foreground">{t("verification.label")} · </b>
          <span className={TONE[outcome]}>{t(`verification.${outcome}`)}</span>
        </p>
        {signal && <p className="mt-1 text-[var(--text-2)]">{signal}</p>}
        {check && (
          <p className={cn("mt-1 text-[var(--text-2)]", outcome === "failed" && "text-[var(--danger)]")}>
            {name(check.actor)} · <Prose text={say(check.line)} />
          </p>
        )}
        {series && <SignalChart series={series} approvedAt={approvedAt} />}
      </div>
    </li>
  );
}
