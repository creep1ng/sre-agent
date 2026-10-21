import { CheckIcon, OctagonXIcon, RotateCcwIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { AgentAvatar } from "@/components/brand";
import { ToneBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { formatClock, plural } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { AgentJob, Incident } from "@/lib/types";
import { SOURCE_LABEL } from "@/lib/vocabulary";
import { FindingRow, SourceIcon } from "./findings";
import { Panel } from "./panel";

function WorkingAvatar() {
  return (
    <span className="relative">
      <AgentAvatar className="size-10 rounded-xl" />
      <span className="absolute -right-0.5 -bottom-0.5 size-3 animate-pulse-ring rounded-full border-2 border-card bg-info text-info" />
    </span>
  );
}

/** Live list of what the agent did and is doing. Only real steps, never a fake plan. */
function JobSteps({ job }: { job: AgentJob }) {
  const now = useNow();
  const current = job.steps[job.done];
  let elapsed = 0;
  return (
    <ol className="flex flex-col" aria-live="polite">
      <AnimatePresence initial={false}>
        {job.steps.slice(0, job.done).map((step, index) => {
          elapsed += step.durationMs;
          const finding = job.findings.find((f) => f.title === step.finding?.title);
          return (
            <motion.li
              key={`${index}-${step.label}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="border-b border-border/60 last:border-b-0"
            >
              {finding ? (
                <FindingRow finding={finding} live />
              ) : (
                <div className="flex items-center gap-3 py-2.5">
                  <span className="flex size-7 items-center justify-center rounded-lg bg-success-soft text-success">
                    <CheckIcon className="size-3.5" />
                  </span>
                  <span className="flex-1 text-sm text-muted-foreground">{step.label}</span>
                  <span className="text-xs text-muted-foreground tabular">{formatClock(elapsed)}</span>
                </div>
              )}
            </motion.li>
          );
        })}
      </AnimatePresence>
      {current && (
        <li className="flex items-center gap-3 py-2.5">
          <SourceIcon source={current.source} className="animate-pulse" />
          <span className="flex-1 text-sm font-medium">
            <span className="text-shimmer">{current.label}…</span>
          </span>
          <span className="text-xs text-muted-foreground">{SOURCE_LABEL[current.source]}</span>
        </li>
      )}
      {!current && (
        <li className="py-2.5 text-sm text-muted-foreground">
          <span className="text-shimmer">Terminando…</span>
        </li>
      )}
      <li className="sr-only">{`Lleva ${formatClock(now - job.startedAt)}`}</li>
    </ol>
  );
}

export function InvestigationPanel({ incident }: { incident: Incident }) {
  const now = useNow();
  const job = incident.job!;
  const title =
    job.kind === "revision"
      ? "El agente está preparando otra propuesta"
      : job.kind === "reinvestigation"
        ? "El agente está investigando de nuevo"
        : "El agente está investigando";
  const description =
    job.kind === "investigation"
      ? "Suele tardar entre 1 y 3 minutos. Puedes salir de aquí: te avisaremos cuando proponga algo."
      : "Tiene en cuenta lo que le dijiste. Te avisaremos cuando la nueva propuesta esté lista.";
  return (
    <Panel
      icon={<WorkingAvatar />}
      title={title}
      description={description}
      meta={
        <span className="flex items-center gap-2">
          {job.findings.length > 0 && (
            <ToneBadge tone="brand">{plural(job.findings.length, "hallazgo", "hallazgos")}</ToneBadge>
          )}
          <span className="rounded-md bg-muted px-2 py-1 font-mono text-xs text-foreground tabular">
            {formatClock(now - job.startedAt)}
          </span>
        </span>
      }
    >
      <JobSteps job={job} />
    </Panel>
  );
}

export function AgentFailurePanel({ incident }: { incident: Incident }) {
  const retry = useStore((s) => s.retryAgent);
  const failure = incident.job!.failure!;
  return (
    <Panel
      tone="critical"
      icon={
        <span className="flex size-10 items-center justify-center rounded-xl bg-critical-soft text-critical">
          <OctagonXIcon className="size-5" />
        </span>
      }
      title={failure.title}
      description={failure.reason}
      footer={
        <>
          <Button onClick={() => retry(incident.id)}>
            <RotateCcwIcon /> Ya lo corregí, reintentar
          </Button>
          <span className="text-sm text-muted-foreground">El incidente sigue abierto; no hace falta declarar otro.</span>
        </>
      }
    >
      <div className="rounded-xl border border-critical-line bg-critical-soft/60 p-4">
        <p className="text-sm font-semibold">Cómo resolverlo</p>
        <p className="mt-1 text-sm">{failure.fix}</p>
      </div>
    </Panel>
  );
}

export function PostmortemDraftingPanel({ incident }: { incident: Incident }) {
  const now = useNow();
  const job = incident.job;
  return (
    <Panel
      icon={<WorkingAvatar />}
      title="El agente está redactando el postmortem"
      description="Lo escribe con la historia del incidente: qué pasó, por qué, qué hiciste y qué falta. Tú lo revisas antes de cerrar."
      meta={
        job && (
          <span className="rounded-md bg-muted px-2 py-1 font-mono text-xs text-foreground tabular">
            {formatClock(now - job.startedAt)}
          </span>
        )
      }
    >
      {job && <JobSteps job={job} />}
    </Panel>
  );
}
