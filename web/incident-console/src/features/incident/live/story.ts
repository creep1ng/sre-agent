import incident from "@/i18n/es/incident";
import type { ChangeEvent, Evidence, Mitigation } from "@/lib/incident-api";
import type { LiveIncident } from "@/lib/live-incident";
import type { Result } from "./result";

/*
 * The incident's story from what the API recorded: run events, the reasoning (hypothesis,
 * evidence with its verdict, mitigation) and the service's recent changes. Entries carry catalog
 * keys, so the page tells them in Spanish or English; what the agent wrote (findings, the
 * hypothesis, the plan) is quoted as recorded.
 */

export type Key = keyof typeof incident & string;
/** A message of the `incident` catalog; a param may be another message, and `code` marks identifiers. */
export interface Line {
  key: Key;
  params?: Record<string, string | Line>;
}

/** Measured evidence has a verdict; a recalled incident or a knowledge fragment is context, never a measure. */
export type Verdict = "supports" | "contradicts" | "inconclusive" | "empty" | "memory" | "knowledge";

export interface Actor {
  kind: "you" | "person" | "agent" | "system";
  name?: string;
}

export interface StoryEntry {
  id: string;
  at: number;
  actor: Actor;
  line: Line;
  quote?: string;
  verdict?: Verdict;
  /** The evidence number the hypothesis claims point to. */
  number?: number;
  tone?: "critical";
  /** What the agent asked its source, under a label that names it: a metrics query, a log search… */
  query?: { label: Key; tool: string; text: string; window: string };
  /** What a measured query returned, as the evidence stored it. */
  result?: Result;
  link?: { to: string; external?: boolean };
}

/** Identifiers render as code: `checkout`, `1.5.0`. */
export const code = (value: string) => `\`${value}\``;

type Event = LiveIncident["events"][number];

const SUMMARIES: Record<string, Key | null> = {
  "Triage opened.": "event.triage",
  "Alert dismissed.": "event.dismissed",
  "Alert linked to an existing incident.": "event.linked",
  "Verification failed; returned to investigating.": "event.verifyFailed",
  "Service verified stable.": "event.verified",
  "Postmortem started.": "event.postmortem",
  "Incident closed.": "event.closed",
  "Investigation dispatch started.": "event.working",
  "Investigation dispatch ended: success.": "event.finished",
  "Investigation requested human review.": "event.human",
  "Investigation concluded.": "event.concluded",
  "Investigation concluded; the run ended.": null,
  "Mitigation proposed.": null,
};
/** Human decisions, told in the second person when they are yours. */
const HUMAN: Record<string, string> = {
  "Incident declared.": "event.declared",
  "Investigation started.": "event.started",
  "Investigation continued.": "event.retried",
  "Mitigation approved.": "event.approved",
  "Mitigation sent back for changes.": "event.rejected",
};

/** Why an approval did not run (#923): the incident and the run stay as they were. */
const NOT_APPLIED = new Set(["precondition_failed", "operation_not_authorized", "executor_unavailable", "execution_failed"]);
const OUTCOMES = new Set(["rolled_back", "restarted", "flag_set", "already_at_target"]);

/** What the deploy-executor ran on approval, from its receipt: operation, service, outcome, before → after. */
export function executionLine(mitigation: Mitigation | null | undefined): Line | null {
  const ran = mitigation?.execution;
  const operation = mitigation?.operation;
  if (!ran || !operation) return null;
  const parameters = operation.parameters ?? {};
  const change =
    ran.before_image && ran.after_image
      ? `${code(ran.before_image)} → ${code(ran.after_image)}`
      : parameters.flag
        ? `${code(parameters.flag)} → ${code(parameters.variant ?? "")}`
        : "";
  const outcome = OUTCOMES.has(ran.outcome) ? { key: `receipt.outcome.${ran.outcome}` as Key } : code(ran.outcome);
  return { key: change ? "receipt.ran.change" : "receipt.ran", params: { operation: code(operation.operation), service: code(operation.service), outcome, change } };
}

/** A cause the catalog words, else the generic one: every ending has a cause. */
function cause(code: string | null | undefined): Line {
  return { key: code && `cause.${code}` in incident ? (`cause.${code}` as Key) : "cause.unknown" };
}

const failedDispatch = (event: Event) =>
  event.summary.startsWith("Investigation dispatch ended:") && !event.summary.endsWith("success.");

function actorOf(event: Event, me: string | null | undefined): Actor {
  if (event.actor.type === "agent") return { kind: "agent" };
  if (event.actor.type === "system") return { kind: "system" };
  const reference = event.actor.reference;
  // Until the console knows who you are, every person is you, as in a single-operator console.
  if (me === undefined || (reference?.principal_id ?? null) === me) return { kind: "you" };
  return { kind: "person", name: reference?.display_name ?? reference?.principal_id ?? undefined };
}

function eventEntry(event: Event, live: LiveIncident, me: string | null | undefined): StoryEntry | null {
  const base = { id: `step-${event.event_id}`, at: Date.parse(event.occurred_at), actor: actorOf(event, me) };
  if (failedDispatch(event)) {
    const key = event.reason_code === "run_start_not_authorized" ? "event.notStarted" : "event.stopped";
    return { ...base, line: { key, params: { cause: cause(event.reason_code) } }, tone: "critical" };
  }
  if (event.summary.startsWith("Authorization denied")) {
    return { ...base, line: { key: "event.denied", params: { cause: cause("denied") } }, tone: "critical" };
  }
  if (event.summary.startsWith("Investigation run ended:")) {
    // One ending per run: a failed dispatch already told its cause.
    if (live.events.some((other) => other.run_id === event.run_id && failedDispatch(other))) return null;
    const reason = live.runs.find((run) => run.run_id === event.run_id)?.terminated_reason ?? null;
    return { ...base, line: { key: "event.stopped", params: { cause: cause(reason) } }, tone: "critical" };
  }
  if (event.summary.startsWith("Approval not applied:") && NOT_APPLIED.has(event.reason_code ?? "")) {
    const key = base.actor.kind === "you" ? "event.notApplied.you" : "event.notApplied";
    return { ...base, line: { key, params: { cause: cause(event.reason_code) } }, tone: "critical" };
  }
  // An approval that ran an operation says so in its summary (#923); the receipt tells the rest.
  const human = HUMAN[event.summary] ?? (event.summary.startsWith("Mitigation approved;") ? "event.approved" : undefined);
  // Only a person retries; the agent continuing within a run is not a story entry.
  if (human && event.actor.type === "human") {
    return { ...base, line: { key: (base.actor.kind === "you" ? `${human}.you` : human) as Key } };
  }
  const key = SUMMARIES[event.summary];
  return key ? { ...base, line: { key } } : null;
}

/** The stored query, when there is one: a recalled memory's postmortem, a knowledge fragment's address. */
function queryOf(item: Evidence, label: Key): StoryEntry["query"] {
  return item.query ? { label, tool: item.tool ?? item.source, text: item.query, window: item.time_window ?? "" } : undefined;
}

/** A recalled memory (#773) names the closed incident whose postmortem it came from. */
const MEMORY = /^\/v1\/incidents\/([^/]+)\/postmortem$/;

function evidenceEntry(item: Evidence, cited: Set<string>, service: string): StoryEntry {
  const base = { id: `step-${item.evidence_id}`, at: Date.parse(item.collected_at ?? ""), actor: { kind: "agent" } as Actor };
  const params = { service: code(service), source: item.source };
  if (item.source === "incident_memory") {
    const memory = MEMORY.exec(item.query ?? "");
    const link = memory ? { to: `/incidentes/${memory[1]}` } : undefined;
    const query = queryOf(item, "evidence.query.memory");
    return { ...base, line: { key: "evidence.memory", params }, verdict: "memory", quote: item.finding ?? item.summary, link, query };
  }
  if (item.source === "bok" || item.tool === "bok.search") {
    const query = queryOf(item, "evidence.query.knowledge");
    return { ...base, line: { key: "evidence.knowledge" }, verdict: "knowledge", quote: item.finding ?? item.summary, query };
  }
  const key: Key =
    item.tool === "query_prometheus"
      ? "evidence.metrics"
      : item.tool === "query_elasticsearch"
        ? "evidence.logs"
        : item.source === "change-events"
          ? "evidence.changes"
          : "evidence.other";
  // A verdict was judged against the hypothesis that cites it; a query that found nothing was
  // measured by the harness, so it always shows (#707).
  const verdict = item.empty ? "empty" : item.verdict && cited.has(item.evidence_id) ? item.verdict : undefined;
  return {
    ...base,
    line: { key, params },
    verdict,
    quote: (verdict && item.finding) || undefined,
    query: queryOf(item, key.replace("evidence.", "evidence.query.") as Key),
    result: item.summary && !item.empty ? { tool: item.tool ?? item.source, summary: item.summary } : undefined,
  };
}

const CHANGE: Record<ChangeEvent["kind"], Key> = { deploy: "change.deploy", rollback: "change.rollback", ci: "change.ci" };

function changeEntry(change: ChangeEvent): StoryEntry {
  return {
    id: `step-${change.change_id}`,
    at: Date.parse(change.occurred_at),
    actor: { kind: "system", name: change.author ?? undefined },
    line: { key: CHANGE[change.kind], params: { service: code(change.service), version: change.version ? code(change.version) : "" } },
    tone: change.status === "failed" ? "critical" : undefined,
    link: change.url?.startsWith("https://") ? { to: change.url, external: true } : undefined,
  };
}

/** The story in chronological order; evidence is numbered in that order. `me` is your principal, once known. */
export function buildStory(live: LiveIncident, me?: string | null): StoryEntry[] {
  const reasoning = typeof live.reasoning === "object" ? live.reasoning : null;
  const service = live.detail?.alert?.service ?? "";
  const hypothesis = reasoning?.hypotheses.at(-1);
  const cited = new Set([...(hypothesis?.supporting_evidence ?? []), ...(hypothesis?.contradicting_evidence ?? [])]);
  const entries: (StoryEntry | null)[] = [
    ...live.events.map((event) => eventEntry(event, live, me)),
    ...(reasoning?.evidence ?? []).map((item) => evidenceEntry(item, cited, service)),
    ...(reasoning?.hypotheses ?? []).map((item) => ({
      id: `step-${item.hypothesis_id}`,
      at: Date.parse(item.created_at ?? ""),
      actor: { kind: "agent" } as Actor,
      line: { key: "event.hypothesis" } as Line,
      quote: item.statement,
    })),
    ...(Array.isArray(live.changes) ? live.changes.map(changeEntry) : []),
  ];
  const mitigation = reasoning?.mitigation_strategy;
  if (mitigation) {
    const at = Date.parse(mitigation.created_at ?? "");
    entries.push({ id: "step-mitigation", at, actor: { kind: "agent" }, line: { key: "event.mitigation" }, quote: mitigation.description });
  }
  const executed = executionLine(mitigation);
  if (executed) {
    entries.push({ id: "step-execution", at: Date.parse(mitigation!.execution!.executed_at), actor: { kind: "system", name: "deploy-executor" }, line: executed });
  }
  const story = entries.filter((entry): entry is StoryEntry => entry !== null && Number.isFinite(entry.at)).sort((a, b) => a.at - b.at);
  let number = 0;
  for (const entry of story) if (entry.line.key.startsWith("evidence.")) entry.number = ++number;
  return story;
}

/** The evidence the current hypothesis cites, supporting first, as numbered story entries. */
export function claimsOf(live: LiveIncident, story: StoryEntry[]): StoryEntry[] {
  const hypothesis = typeof live.reasoning === "object" ? live.reasoning?.hypotheses.at(-1) : undefined;
  const ids = [...(hypothesis?.supporting_evidence ?? []), ...(hypothesis?.contradicting_evidence ?? [])];
  return ids.flatMap((id) => story.find((entry) => entry.id === `step-${id}`) ?? []);
}
