import { ArrowLeftIcon, CircleCheckIcon } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { formatDayTime } from "@/lib/format";
import type { Alert, Incident } from "@/lib/types";
import { ClosureTimeline } from "./closure";
import { CopyMarkdownButton, PostmortemDocument } from "./postmortem";
import { Panel } from "./panel";

export function ClosedPanel({ incident, alert }: { incident: Incident; alert: Alert }) {
  const now = useNow();
  const doc = incident.postmortem?.doc;
  return (
    <div className="flex flex-col gap-6">
      <Panel
        tone="success"
        icon={
          <span className="flex size-10 items-center justify-center rounded-xl bg-success-soft text-success">
            <CircleCheckIcon className="size-5" />
          </span>
        }
        title="Incidente cerrado"
        meta={`Cerrado ${formatDayTime(incident.closedAt!, now)}`}
        description="El postmortem quedó aprobado y forma parte del historial."
        footer={
          <>
            <Button asChild>
              <Link to="/">
                <ArrowLeftIcon /> Volver a la bandeja
              </Link>
            </Button>
            {doc && <CopyMarkdownButton incident={incident} doc={doc} />}
          </>
        }
      >
        <div className="border-t pt-5">
          <ClosureTimeline incident={incident} alert={alert} />
        </div>
      </Panel>
      {doc && <PostmortemDocument incident={incident} doc={doc} readOnly />}
    </div>
  );
}
