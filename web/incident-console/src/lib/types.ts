export type Severity = "sev1" | "sev2" | "sev3" | "sev4";
export type ScenarioKey = "payments" | "recommendations" | "ads" | "cart" | "images";

export type AlertStatus = "new" | "declared" | "linked" | "dismissed";

export interface SignalSpec {
  /** Human name of the measured signal, e.g. "Pagos con error". */
  label: string;
  unit: "%" | "s";
  threshold: number;
  baseline: number;
  peak: number;
  /** Upper bound of the chart's y axis. */
  max: number;
}

export interface Alert {
  id: string;
  scenario: ScenarioKey;
  title: string;
  summary: string;
  service: string;
  severity: Severity;
  /** When the signal started to fail. */
  startedAt: number;
  /** When the rule fired. */
  detectedAt: number;
  signal: SignalSpec;
  rule: string;
  source: string;
  suggestedImpact: string;
  status: AlertStatus;
  incidentId?: string;
  dismissReason?: string;
  dismissedAt?: number;
  /** Set when the signal recovers (mitigation applied). */
  recoveryStartAt?: number;
}

/** States of agent/workflows/incident-response.yaml that an incident goes through. */
export type WorkflowState =
  | "investigating"
  | "mitigating"
  | "verifying"
  | "resolved"
  | "postmortem"
  | "closed";

export type EvidenceSource = "metrics" | "logs" | "traces" | "changes" | "knowledge" | "reasoning";

export type Verdict = "supports" | "empty" | "contradicts" | "context";

export interface Finding {
  id: string;
  source: EvidenceSource;
  title: string;
  detail: string;
  verdict: Verdict;
  query?: { tool: string; text: string; window: string };
  at: number;
}

export interface AgentStep {
  label: string;
  source: EvidenceSource;
  durationMs: number;
  finding?: Omit<Finding, "id" | "at">;
}

export interface AgentFailure {
  title: string;
  reason: string;
  fix: string;
  at: number;
}

export type JobKind = "investigation" | "revision" | "reinvestigation" | "postmortem";

export interface AgentJob {
  kind: JobKind;
  /** 1-based number of the investigation this job belongs to. */
  ordinal: number;
  startedAt: number;
  steps: AgentStep[];
  done: number;
  findings: Finding[];
  /** Proposal the job publishes when it ends (revisions carry the human comment). */
  draft?: ProposalDraftRef;
  /** Failure scenario: the job stops this long after it starts. */
  failAfterMs?: number;
  failure?: AgentFailure;
}

export type ProposalDraftRef = Pick<
  Proposal,
  "summary" | "steps" | "risk" | "riskNote" | "verification" | "revisionNote"
>;

export type Confidence = "low" | "medium" | "high";

export interface Hypothesis {
  statement: string;
  confidence: Confidence;
  refutedIf: string;
}

export type DecisionOutcome = "approved" | "changes_requested" | "rejected";

export interface Proposal {
  id: string;
  number: number;
  createdAt: number;
  hypothesis: Hypothesis;
  findings: Finding[];
  summary: string;
  steps: string[];
  risk: "low" | "medium" | "high";
  riskNote: string;
  verification: string;
  revisionNote?: string;
  decision?: { outcome: DecisionOutcome; comment?: string; at: number };
}

export interface Verification {
  checklist: boolean[];
  appliedAt?: number;
  stableSuggestedAt?: number;
  confirmedAt?: number;
}

export type Certainty = "confirmed" | "probable" | "hypothesis" | "unknown";

export interface PostmortemDoc {
  summary: string;
  impact: string;
  cause: { statement: string; certainty: Certainty };
  actions: string[];
  verification: string;
  timeline: { at: number; text: string }[];
  pending: string[];
  unknowns: string[];
}

export interface Postmortem {
  status: "drafting" | "review" | "approved";
  doc?: PostmortemDoc;
  draftedAt?: number;
  editedAt?: number;
  approvedAt?: number;
}

export type Actor = "system" | "you" | "agent";

export interface TimelineEvent {
  id: string;
  at: number;
  actor: Actor;
  text: string;
  detail?: string;
  tone?: "default" | "success" | "warning" | "critical";
  /** milestone: key moment kept in the postmortem chronology. */
  kind?: "milestone" | "finding" | "note";
}

export interface Incident {
  id: string;
  number: number;
  /** Opaque ids of the real backend; shown only in "Detalles técnicos". */
  backendId: string;
  title: string;
  service: string;
  severity: Severity;
  impact: string;
  scenario: ScenarioKey;
  alertIds: string[];
  declaredAt: number;
  state: WorkflowState;
  job?: AgentJob;
  investigations: number;
  proposals: Proposal[];
  verification?: Verification;
  postmortem?: Postmortem;
  events: TimelineEvent[];
  resolvedAt?: number;
  closedAt?: number;
  runIds: string[];
}

export interface Settings {
  agentFailure: boolean;
}
