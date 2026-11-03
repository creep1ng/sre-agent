import { CheckIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import type { LiveIncident } from "@/lib/live-incident";
import { cn } from "@/lib/utils";
import { Prose, useActorName, useSay, useWhen } from "./say";
import { REINVESTIGATIONS, type StoryEntry } from "./story";
import type { Choice, DecisionError } from "./use-decision";

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
  /** What the mitigation was expected to bring back: the plan's own verification check. */
  expected?: string;
  /** Failed verifications of the incident so far: past REINVESTIGATIONS the agent stops retrying (#710). */
  failed: number;
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
  const expected = typeof live.reasoning === "object" ? live.reasoning?.mitigation_strategy?.verification_check : undefined;
  const failed = story.filter((entry) => entry.line.key === "event.verifyFailed").length;
  return { at, outcome, approvedAt, resolvedAt, firing, check, expected, failed };
}

/** "95 s", "4 min", "2 h": how long the signal took to recover. */
export function span(ms: number): string {
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
  const { outcome, resolvedAt, approvedAt, check, firing, expected, series } = verification;
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
        {/* A failed verification, by the agent or by a person, says what was not met and what follows (#710). */}
        {outcome === "failed" && (
          <p className="mt-1 text-[var(--text-2)]">
            {expected && (
              <>
                {t("verification.failed.expected")} <Prose text={expected} />{" "}
              </>
            )}
            {verification.failed > REINVESTIGATIONS ? (
              <span className="text-[var(--danger)]">{t("event.gaveUp", { failed: verification.failed })}</span>
            ) : (
              t("verification.failed.next")
            )}
          </p>
        )}
        {series && <SignalChart series={series} approvedAt={approvedAt} />}
      </div>
    </li>
  );
}

interface StabilityProps {
  expected?: string;
  sending: Choice | null;
  error: DecisionError | null;
  canDecide: boolean;
  onDecide: (choice: "stable" | "failing") => void;
}

/**
 * Whether the executed mitigation worked, asked of you while the incident waits for a verdict
 * (#710): the fallback to the agent's own verification, a decision and so in amber.
 */
export function StabilityCheck({ expected, sending, error, canDecide, onDecide }: StabilityProps) {
  const t = useT("incident");
  return (
    <section
      aria-label={t("stability.label")}
      data-decision=""
      className="overflow-hidden rounded-2xl border border-star bg-[color-mix(in_oklab,var(--star)_8%,transparent)]"
    >
      <div className="px-[30px] pt-7 pb-5">
        <h2 className="font-display text-[30px] leading-[1.1] tracking-[-0.01em]">{t("stability.title")}</h2>
        {expected && (
          <p className="mt-3 text-[var(--text-2)]">
            {t("stability.expected")} <Prose text={expected} />
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2.5 border-t border-star px-[18px] py-4">
        {error && (
          <span role="alert" className="mr-auto text-sm text-[var(--danger)]">
            {t(`decision.${error}`)}
          </span>
        )}
        <Button variant="outline" size="lg" className="font-mono" disabled={!canDecide || sending !== null} onClick={() => onDecide("failing")}>
          {t("stability.failing")}
        </Button>
        <Button size="lg" className="bg-star font-mono text-on-star hover:bg-star/90" disabled={!canDecide || sending !== null} onClick={() => onDecide("stable")}>
          {t("stability.stable")}
        </Button>
      </div>
    </section>
  );
}
