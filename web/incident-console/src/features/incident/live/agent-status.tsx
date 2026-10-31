import { ArrowUpRightIcon, OctagonXIcon, PlayIcon, RotateCcwIcon } from "lucide-react";
import { AgentAvatar } from "@/components/brand";
import { ToneBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { formatClock } from "@/lib/format";
import type { LiveIncident } from "@/lib/live-incident";
import { CONFIDENCE, RISK, type Tone } from "@/lib/vocabulary";
import { Panel, PanelSection } from "../panel";
import { endingCause } from "./causes";

export type AgentStatus =
  | { kind: "idle" }
  | { kind: "working"; since: number }
  | { kind: "waiting"; run: string }
  | { kind: "stopped"; cause: string }
  | { kind: "other"; state: string };

export const STATUS_LABEL: Record<AgentStatus["kind"], { label: string; tone: Tone }> = {
  idle: { label: "Sin investigar", tone: "neutral" },
  working: { label: "Investigando…", tone: "info" },
  waiting: { label: "Esperando tu decisión", tone: "brand" },
  stopped: { label: "Detenido", tone: "critical" },
  other: { label: "En curso", tone: "neutral" },
};

/** The triage run stays open in `active`; an investigation run moves past it. */
const investigation = (run: { current_state: string }) => run.current_state !== "triage" && run.current_state !== "active";

export function agentStatus(live: LiveIncident): AgentStatus {
  const runs = live.runs.filter(investigation);
  const run = runs.at(-1);
  const state = live.detail?.state ?? "";
  if (live.starting || (run?.status === "running" && run.current_state === "investigating")) {
    // Until the requested run shows up, the clock counts from the click.
    if (live.requested && live.runs.at(-1)?.run_id === live.requested.after) return { kind: "working", since: live.requested.at };
    const first = live.events.find((event) => event.run_id === run?.run_id);
    return { kind: "working", since: first ? Date.parse(first.occurred_at) : Date.now() };
  }
  if (!run) return state === "active" ? { kind: "idle" } : { kind: "other", state };
  // A denied run stored before #788 waits for `escalate`, which nothing accepts: it stopped.
  const escalated = run.pending_command === "escalate";
  if (run.status === "awaiting_human" && !escalated) return { kind: "waiting", run: run.run_id };
  if (state === "investigating") {
    const events = live.events.filter((event) => event.run_id === run.run_id);
    return { kind: "stopped", cause: endingCause(events, escalated ? "denied" : run.terminated_reason) };
  }
  return { kind: "other", state };
}

function Working({ since }: { since: number }) {
  const now = useNow();
  return (
    <span className="rounded-md bg-muted px-2 py-1 font-mono text-xs text-foreground tabular">
      {formatClock(now - since)}
    </span>
  );
}

function StartButton({ live, onStart, label }: { live: LiveIncident; onStart: () => void; label: string }) {
  return (
    <>
      <Button onClick={onStart} disabled={live.starting}>
        {label === "Investigar" ? <PlayIcon /> : <RotateCcwIcon />} {label}
      </Button>
      {live.startError && (
        <span role="alert" className="text-sm text-critical">
          {live.startError}
        </span>
      )}
    </>
  );
}

export function AgentStatusPanel({ live, status, onStart }: { live: LiveIncident; status: AgentStatus; onStart: () => void }) {
  const reasoning = live.reasoning === "forbidden" ? null : live.reasoning;
  const hypothesis = reasoning?.hypotheses.at(-1);
  const mitigation = reasoning?.mitigation_strategy;
  const avatar = <AgentAvatar className="size-10 rounded-xl" />;
  if (status.kind === "working") {
    return (
      <Panel
        icon={avatar}
        title={<span className="text-shimmer">Investigando…</span>}
        meta={<Working since={status.since} />}
      />
    );
  }
  if (status.kind === "idle") {
    return (
      <Panel
        icon={avatar}
        title="Sin investigar"
        footer={<StartButton live={live} onStart={onStart} label="Investigar" />}
      />
    );
  }
  if (status.kind === "stopped") {
    return (
      <Panel
        tone="critical"
        icon={
          <span className="flex size-10 items-center justify-center rounded-xl bg-critical-soft text-critical">
            <OctagonXIcon className="size-5" />
          </span>
        }
        title={`Detenido: ${status.cause}`}
        footer={<StartButton live={live} onStart={onStart} label="Reintentar investigación" />}
      />
    );
  }
  return (
    <Panel
      tone={status.kind === "waiting" ? "attention" : "default"}
      icon={avatar}
      title={status.kind === "waiting" ? "Esperando tu decisión" : "El agente terminó por ahora"}
      footer={
        // Deciding on the mitigation stays in the previous console until #709/#710.
        status.kind === "waiting" && (
          <a
            href={`/?view=decisions&incident_id=${encodeURIComponent(live.detail?.incident_id ?? "")}&run_id=${encodeURIComponent(status.run)}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline dark:text-brand-line"
          >
            Abrir en Decisiones <ArrowUpRightIcon className="size-4" aria-hidden="true" />
          </a>
        )
      }
    >
      {live.reasoning === "forbidden" && (
        <p className="text-sm text-muted-foreground">Tu credencial no permite leer el razonamiento del agente.</p>
      )}
      {hypothesis && (
        <PanelSection
          title="Hipótesis"
          aside={<ToneBadge tone="brand">{CONFIDENCE[hypothesis.confidence]?.label ?? hypothesis.confidence}</ToneBadge>}
        >
          <p className="text-[15px]">{hypothesis.statement}</p>
        </PanelSection>
      )}
      {mitigation && (
        <PanelSection
          title="Mitigación propuesta"
          className="mt-4"
          aside={mitigation.risk && <ToneBadge tone={RISK[mitigation.risk].tone}>{RISK[mitigation.risk].label}</ToneBadge>}
        >
          <p className="text-[15px]">{mitigation.description}</p>
          {mitigation.steps && mitigation.steps.length > 0 && (
            <ol className="mt-2 flex flex-col gap-1 text-sm text-muted-foreground">
              {mitigation.steps.map((step, index) => (
                <li key={step} className="flex gap-2">
                  <span className="font-semibold text-foreground tabular">{index + 1}.</span>
                  {step}
                </li>
              ))}
            </ol>
          )}
        </PanelSection>
      )}
    </Panel>
  );
}
