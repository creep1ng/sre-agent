import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { AgentFailurePanel, InvestigationPanel, PostmortemDraftingPanel } from "@/features/incident/agent-work";
import { ClosedPanel } from "@/features/incident/closed-panel";
import { IncidentHeader } from "@/features/incident/header";
import { PostmortemReviewPanel } from "@/features/incident/postmortem";
import { ProposalPanel } from "@/features/incident/proposal-panel";
import { RecoveryPanel } from "@/features/incident/recovery-panel";
import { LifecycleStepper } from "@/features/incident/stepper";
import { StoryRail } from "@/features/incident/story-panel";
import { useIncident } from "@/lib/selectors";
import { alertsOf, useStore } from "@/lib/store";
import type { Alert, Incident } from "@/lib/types";

function nowPanel(incident: Incident, alert: Alert): { key: string; node: ReactNode } {
  switch (incident.state) {
    case "investigating":
      return incident.job?.failure
        ? { key: "failure", node: <AgentFailurePanel incident={incident} /> }
        : { key: `investigation-${incident.investigations}`, node: <InvestigationPanel incident={incident} /> };
    case "mitigating":
      return { key: `proposal-${incident.proposals.length}`, node: <ProposalPanel incident={incident} /> };
    case "verifying":
      return { key: "recovery", node: <RecoveryPanel incident={incident} alert={alert} /> };
    case "resolved":
    case "postmortem":
      return incident.postmortem?.status === "review"
        ? { key: "postmortem-review", node: <PostmortemReviewPanel incident={incident} /> }
        : { key: "postmortem-drafting", node: <PostmortemDraftingPanel incident={incident} /> };
    case "closed":
      return { key: "closed", node: <ClosedPanel incident={incident} alert={alert} /> };
  }
}

export function IncidentPage() {
  const { incidentId } = useParams();
  const incident = useIncident(incidentId);
  const allAlerts = useStore((s) => s.alerts);

  if (!incident) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
        <h1 className="font-display text-3xl">No encontramos ese incidente</h1>
        <p className="mt-2 text-muted-foreground">Puede que el escenario se haya reiniciado.</p>
        <Button asChild className="mt-6">
          <Link to="/">Ir a la bandeja</Link>
        </Button>
      </div>
    );
  }

  const alerts = alertsOf({ alerts: allAlerts }, incident);
  const alert = alerts[0];
  const panel = nowPanel(incident, alert);
  return (
    <div className="lg:grid lg:min-h-dvh lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="mx-auto w-full max-w-5xl min-w-0 px-4 py-6 sm:px-8 lg:py-8">
        <IncidentHeader incident={incident} alert={alert} />
        <div className="mt-7 rounded-2xl border bg-card/60 px-4 py-4 shadow-xs">
          <LifecycleStepper incident={incident} />
        </div>
        <div className="mt-6 min-w-0">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={panel.key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.25, ease: [0.2, 0, 0, 1] }}
            >
              {panel.node}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
      <StoryRail incident={incident} alerts={alerts} />
    </div>
  );
}
