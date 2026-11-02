import { ClockIcon, PlayIcon, RotateCcwIcon } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { ConnectDialog } from "@/features/inbox/connect-dialog";
import { Decisions, decisionsOf } from "@/features/incident/live/decisions";
import { HypothesisProse } from "@/features/incident/live/hypothesis";
import { Proposal, operationCall } from "@/features/incident/live/proposal";
import { Prose, Stamp } from "@/features/incident/live/say";
import { PHASES, agentStatus, phaseOf, type AgentStatus } from "@/features/incident/live/status";
import { buildStory, claimsOf, code } from "@/features/incident/live/story";
import { Timeline } from "@/features/incident/live/timeline";
import { useDecision } from "@/features/incident/live/use-decision";
import { verificationOf } from "@/features/incident/live/verification";
import { useT } from "@/i18n";
import { useLiveIncident, type IncidentPhase, type LiveIncident } from "@/lib/live-incident";
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

function Phases({ state, waiting }: { state: string; waiting: boolean }) {
  const t = useT("incident");
  const current = phaseOf(state);
  return (
    <ol aria-label={t("phases")} className="mt-8 mb-12 flex border-t font-mono text-[13px] text-[var(--dim)]">
      {PHASES.map((phase, index) => (
        <li
          key={phase}
          aria-current={index === current ? "step" : undefined}
          data-decision={waiting && index === current ? "" : undefined}
          className={cn(
            "relative flex-1 pt-3.5 before:absolute before:inset-x-0 before:-top-px before:h-0.5",
            index < current && "text-[var(--mist)] before:bg-[var(--mist)]",
            index === current && (waiting ? "text-star-ink before:bg-star" : "text-foreground before:bg-[var(--mist)]"),
          )}
        >
          {t(`phase.${phase}`)}
        </li>
      ))}
    </ol>
  );
}

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
  if (live.phase !== "ready" || !live.detail) return <Blocked phase={live.phase === "ready" ? "loading" : live.phase} />;

  const { detail } = live;
  const status = agentStatus(live);
  const story = buildStory(live, decision.me);
  const reasoning = typeof live.reasoning === "object" ? live.reasoning : null;
  const hypothesis = reasoning?.hypotheses.at(-1);
  const mitigation = reasoning?.mitigation_strategy;
  const operation = mitigation ? operationCall(mitigation) : null;
  const decisions = decisionsOf(live, story);
  const waiting = status.kind === "waiting";
  // The report changes with the incident and its runs, never with the page's own polling.
  const updated = Math.max(
    Date.parse(detail.updated_at),
    ...live.runs.map((run) => Date.parse(run.updated_at)),
    ...live.events.map((event) => Date.parse(event.occurred_at)),
  );
  return (
    <article className="mx-auto w-full max-w-4xl min-w-0 px-4 py-8 sm:px-8 lg:px-14 lg:py-12">
      <p className="mb-4 flex flex-wrap gap-3.5 font-mono text-[13px] font-medium text-[var(--mist)]">
        {detail.alert && <Prose text={code(detail.alert.service)} />}
        {detail.severity && <span>{detail.severity.toUpperCase()}</span>}
        <span data-decision={waiting ? "" : undefined} className={cn(waiting && "text-star-ink", status.kind === "stopped" && "text-[var(--danger)]")}>{t(`status.${status.kind}`)}</span>
        {Number.isFinite(updated) && (
          <span className="inline-flex items-center gap-1.5">
            <ClockIcon className="size-3.5" aria-hidden="true" />
            <span className="sr-only">{t("updated")}</span>
            <Stamp at={updated} />
          </span>
        )}
        {live.stale && <span className="text-[var(--danger)]">{t("stale")}</span>}
      </p>
      <h1 className="max-w-[18ch] font-display text-4xl leading-none font-light tracking-[-0.03em] sm:text-[54px]">
        {detail.alert?.summary ?? t("status.untitled")}
      </h1>
      <Phases state={detail.state} waiting={waiting} />
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
      {decisions.length > 0 && (
        <div className="mb-14">
          <Decisions decisions={decisions} mitigation={mitigation} />
        </div>
      )}
      <details className="border-t pt-4 text-sm text-[var(--dim)]">
        <summary className="cursor-pointer">{t("technical")}</summary>
        <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 font-mono text-xs">
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
