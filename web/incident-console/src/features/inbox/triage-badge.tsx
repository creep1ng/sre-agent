import { ToneBadge } from "@/components/badges";
import type { TriageStatus } from "@/lib/types";
import { TRIAGE } from "@/lib/vocabulary";

export function TriageBadge({ status }: { status: TriageStatus }) {
  const meta = TRIAGE[status];
  return <ToneBadge tone={meta.tone}>{meta.label}</ToneBadge>;
}
