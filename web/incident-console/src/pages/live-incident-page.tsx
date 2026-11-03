import { PlayIcon, RotateCcwIcon } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { Decisions, decisionsOf } from "@/features/incident/live/decisions";
import { HypothesisProse } from "@/features/incident/live/hypothesis";
import { ClosingSummary, PostmortemDraft } from "@/features/incident/live/postmortem";
import { Proposal, operationCall } from "@/features/incident/live/proposal";
import { Prose, Stamp } from "@/features/incident/live/say";
import { PHASES, agentStatus, phaseOf, phaseTimes, type AgentStatus } from "@/features/incident/live/status";
import { buildStory, claimsOf, code } from "@/features/incident/live/story";
import { Timeline } from "@/features/incident/live/timeline";
import { useDecision } from "@/features/incident/live/use-decision";
import { StabilityCheck, verificationOf } from "@/features/incident/live/verification";
import { useT } from "@/i18n";
import { useLiveIncident, type IncidentPhase, type LiveIncident } from "@/lib/live-incident";
import { useIncidentTitle } from "@/lib/title";
import { cn } from "@/lib/utils";

function Blocked({ phase }: { phase: Exclude<IncidentPhase, "ready"> }) {
  const t = useT("incident");
  const [connectOpen, setConnectOpen] = useState(false);
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
      <h1 className="font-display text-3xl">{t(`blocked.${phase}`)}</h1>
      {phase === "unauthenticated" || phase === "auth" ? (
        <Button className="mt-6" onClick={() => setConnectOpen(true)}>
          {t("blocked.connect")}
        </Button>
      ) : (
        phase !== "loading" && (
          <Button asChild className="mt-6" variant="secondary">
            <Link to="/">{t("blocked.inbox")}</Link>
          </Button>
        )
      )}
      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </div>
  );
}

function Phases({ state, waiting, times }: { state: string; waiting: boolean; times: (number | null)[] }) {
  const t = useT("incident");
  const current = phaseOf(state);
  return (
    <ol aria-label={t("phases")} className="mt-8 mb-12 grid grid-cols-3 gap-x-3 gap-y-5 font-mono text-[13px] text-[var(--dim)] sm:grid-cols-6">
      {PHASES.map((phase, index) => {
        const at = index <= current ? times[index] : null;
        return (
          <li
            key={phase}
            aria-current={index === current ? "step" : undefined}
            data-decision={waiting && index === current ? "" : undefined}
            className={cn(
              "relative min-w-0 border-t pt-3 before:absolute before:inset-x-0 before:-top-px before:h-0.5",
              index < current && "text-[var(--mist)] before:bg-[var(--mist)]",
              index === current && (waiting ? "text-star-ink before:bg-star" : "text-foreground before:bg-[var(--mist)]"),
            )}
          >
            <span className="block truncate">{t(`phase.${phase}`)}</span>
            {at !== null && <Stamp at={at} className="mt-0.5 block w-fit text-xs text-[var(--dim)] tabular-nums" />}
          </li>
        );
      })}
    </ol>
  );
}

/** Severity in a colour scale, never amber: amber is a decision waiting. */
const SEVERITY_TONE: Record<string, string> = {
  sev1: "border-transparent bg-[var(--danger)] text-background",
  sev2: "border-[var(--danger)] text-[var(--danger)]",
  sev3: "border-[var(--mist)] text-[var(--mist)]",
  sev4: "border-[var(--dim)] text-[var(--dim)]",
};

/** Investigate when nothing ran yet, retry after a run stopped; never amber, it is not a decision. */
function Start({ live, status }: { live: LiveIncident & { investigate: () => Promise<void> }; status: AgentStatus }) {
  const t = useT("incident");
  if (status.kind !== "idle" && status.kind !== "stopped") return null;
  return (
    <div className="-mt-6 mb-10 flex flex-wrap items-center gap-3">
      <Button variant="outline" onClick={() => void live.investigate()} disabled={live.starting}>
        {status.kind === "idle" ? <PlayIcon /> : <RotateCcwIcon />} {t(status.kind === "idle" ? "action.investigate" : "action.retry")}
      </Button>
      {live.startError && (
        <span role="alert" className="text-sm text-[var(--danger)]">
          {t(`start.${live.startError}`)}
        </span>
      )}
    </div>
  );
}

/** The incident as the API records it: the hypothesis, its evidence and the story so far. */
export function LiveIncidentPage() {
  const { incidentId } = useParams();
  const live = useLiveIncident(incidentId);
  const decision = useDecision(live);
  const t = useT("incident");
  const title = useIncidentTitle();
  if (live.phase !== "ready" || !live.detail) return <Blocked phase={live.phase === "ready" ? "loading" : live.phase} />;

  const { detail } = live;
  const status = agentStatus(live);
  const story = buildStory(live, decision.me);
  const reasoning = typeof live.reasoning === "object" ? live.reasoning : null;
  const hypothesis = reasoning?.hypotheses.at(-1);
  const mitigation = reasoning?.mitigation_strategy;
  const operation = mitigation ? operationCall(mitigation) : null;
  const decisions = decisionsOf(live, story);
  // An executed mitigation waits for a verdict (#710): the agent's verification, else yours.
  const verdict = detail.state === "verifying" && Boolean(mitigation?.execution);
  const verifyingRun = live.runs.findLast((run) => run.current_state === "verifying");
  // The agent's draft waits for a person to approve it and close (#711).
  const postmortemRun = live.runs.findLast((run) => run.current_state === "postmortem");
  const closing = detail.state === "postmortem" && typeof live.postmortem === "object" && Boolean(live.postmortem?.content);
  const waiting = status.kind === "waiting" || verdict || closing;
  const times = phaseTimes(live.events, phaseOf(detail.state));
  // The report changes with the incident and its runs, never with the page's own polling.
  const updated = Math.max(
    Date.parse(detail.updated_at),
    ...live.runs.map((run) => Date.parse(run.updated_at)),
    ...live.events.map((event) => Date.parse(event.occurred_at)),
  );
  return (
    <article className="mx-auto w-full max-w-4xl min-w-0 px-4 py-8 sm:px-8 lg:px-14 lg:py-12">
      <p className="mb-4 flex flex-wrap items-center gap-x-3.5 gap-y-2 font-mono text-[13px] font-medium text-[var(--mist)]">
        {detail.alert && <Prose text={code(detail.alert.service)} />}
        {detail.severity && (
          <span data-severity={detail.severity} className={cn("rounded-full border px-2 py-px text-[12px] leading-[18px] font-semibold", SEVERITY_TONE[detail.severity])}>
            {detail.severity.toUpperCase()}
          </span>
        )}
        <span
          data-status={status.kind}
          data-decision={waiting ? "" : undefined}
          className={cn(waiting && "text-star-ink", status.kind === "stopped" && "text-[var(--danger)]", status.kind === "resolved" && !waiting && "text-[var(--ok)]")}
        >
          {t(`status.${verdict || closing ? "waiting" : status.kind}`)}
        </span>
        {times[0] !== null && (
          <span data-meta="declared" className="font-normal text-[var(--dim)]">
            {t("phase.declared")} <Stamp at={times[0]} className="text-[var(--mist)]" />
          </span>
        )}
        {Number.isFinite(updated) && (
          <span data-meta="updated" className="font-normal text-[var(--dim)]">
            {t("updated")} <Stamp at={updated} className="text-[var(--mist)]" />
          </span>
        )}
        {live.stale && <span className="text-[var(--danger)]">{t("stale")}</span>}
      </p>
      <h1
        data-title={detail.title ? "agent" : "alert"}
        className="max-w-[30ch] font-display text-[32px] leading-[1.1] font-light tracking-[-0.02em] text-balance break-words sm:text-[44px]"
      >
        {title(detail)}
      </h1>
      {detail.alert && (
        <details className="mt-3 max-w-[72ch] text-[13px] text-[var(--dim)]">
          <summary className="cursor-pointer font-mono text-[var(--mist)]">{t("title.alert")}</summary>
          <p className="mt-1.5 leading-relaxed break-words">{detail.alert.summary}</p>
        </details>
      )}
      <Phases state={detail.state} waiting={waiting} times={times} />
      {detail.state === "closed" && <ClosingSummary live={live} />}
      <Start live={live} status={status} />
      {live.reasoning === "forbidden" && <p className="mb-8 text-[var(--dim)]">{t("reasoning.forbidden")}</p>}
      {hypothesis && <HypothesisProse hypothesis={hypothesis} claims={claimsOf(live, story)} />}
      <Timeline story={story} status={status} verification={verificationOf(live, story)} />
      {mitigation && status.kind === "waiting" && detail.state === "mitigating" && (
        <div className="mb-14">
          <Proposal
            mitigation={mitigation}
            sending={decision.sending}
            error={decision.error}
            canDecide={Boolean(decision.me)}
            onDecide={(choice) => void decision.decide(choice, status.run)}
          />
        </div>
      )}
      {verdict && verifyingRun && (
        <div className="mb-14">
          <StabilityCheck
            expected={mitigation?.verification_check}
            sending={decision.sending}
            error={decision.error}
            canDecide={Boolean(decision.me)}
            onDecide={(choice) => void decision.decide(choice, verifyingRun.run_id)}
          />
        </div>
      )}
      {decisions.length > 0 && (
        <div className="mb-14">
          <Decisions
            decisions={decisions}
            mitigation={mitigation}
            basis={reasoning?.hypotheses.find((item) => item.hypothesis_id === mitigation?.based_on_hypothesis) ?? hypothesis}
          />
        </div>
      )}
      {["resolved", "postmortem", "closed"].includes(detail.state) && (
        <PostmortemDraft
          live={live}
          story={story}
          sending={decision.sending !== null}
          error={decision.error}
          canDecide={Boolean(decision.me && postmortemRun)}
          onClose={(version, approved) => postmortemRun && void decision.close(postmortemRun.run_id, version, approved)}
        />
      )}
      <details className="border-t pt-4 text-sm text-[var(--dim)]">
        <summary className="cursor-pointer">{t("technical")}</summary>
        <dl className="mt-3 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-2 font-mono text-xs [&_dd]:break-all">
          <dt>{t("technical.incident")}</dt>
          <dd>{detail.incident_id}</dd>
          <dt>{t("technical.workflow")}</dt>
          <dd>{`incident-response ${detail.workflow_version} · ${detail.state}`}</dd>
          <dt>{t("technical.runs")}</dt>
          <dd>{live.runs.map((run) => `${run.run_id} · ${run.status}`).join(", ")}</dd>
          {operation && <dt>{t("technical.operation")}</dt>}
          {operation && <dd>{operation}</dd>}
          {detail.alert && <dt>{t("technical.alert")}</dt>}
          {detail.alert && <dd>{detail.alert.alert_id}</dd>}
        </dl>
      </details>
    </article>
  );
}
