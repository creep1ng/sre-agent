import type { ChangeEvent, Evidence, RunEvent } from "@/lib/incident-api";
import type { LiveIncident } from "@/lib/live-incident";
import type { Actor, EvidenceSource, Finding } from "@/lib/types";
import { CONFIDENCE, RISK, type Tone } from "@/lib/vocabulary";
import { DISPATCH_CAUSES, TERMINATED, capitalize } from "./causes";

/*
 * The incident's story in Spanish, from what the API recorded: run events, the reasoning
 * (hypothesis, evidence with its verdict, mitigation) and the service's recent changes.
 * The runtime writes event summaries in English; only the ones listed here are told.
 */

export interface StoryEntry {
  id: string;
  at: number;
  actor: Actor;
  text: string;
  detail?: string;
  tone?: "success" | "warning" | "critical";
  badge?: { label: string; tone: Tone };
  source?: EvidenceSource;
  query?: NonNullable<Finding["query"]>;
  /** In-console link (a recalled incident) or an external one (a change's origin). */
  link?: { to: string; external?: boolean };
}

/** Summaries told in the story; `null` hides the ones another entry already tells. */
const SUMMARIES: Record<string, string | null> = {
  "Triage opened.": "Triage abierto",
  "Alert dismissed.": "Alerta descartada",
  "Alert linked to an existing incident.": "Alerta vinculada a este incidente",
  "Incident declared.": "Incidente declarado",
  "Investigation started.": "Investigación solicitada",
  "Investigation continued.": null,
  "Mitigation proposed.": null,
  "Mitigation approved.": "Mitigación aprobada",
  "Mitigation sent back for changes.": "Mitigación devuelta con cambios",
  "Verification failed; returned to investigating.": "La verificación falló; se vuelve a investigar",
  "Service verified stable.": "Servicio verificado estable",
  "Postmortem started.": "Postmortem iniciado",
  "Incident closed.": "Incidente cerrado",
  "Investigation dispatch started.": "Empezó a investigar",
  "Investigation dispatch ended: success.": "Terminó de investigar",
  "Investigation proposed a hypothesis.": "Propuso una hipótesis",
  "Investigation proposed a mitigation.": "Propuso una mitigación",
  "Investigation requested human review.": "Pidió revisión humana",
  "Investigation concluded.": "Concluyó la investigación",
};

const ACTOR: Record<RunEvent["actor"]["type"], Actor> = { human: "you", agent: "agent", system: "system" };

function eventEntry(event: RunEvent, reasoned: boolean): StoryEntry | null {
  const base = { id: event.event_id, at: Date.parse(event.occurred_at), actor: ACTOR[event.actor.type] ?? "system" };
  const cause = event.reason_code ? DISPATCH_CAUSES[event.reason_code] : undefined;
  if (event.kind === "dispatch_receipt" && event.summary.startsWith("Investigation dispatch ended:") && !event.summary.endsWith("success.")) {
    // #704 records why the investigation the declaration should start did not start.
    const text = event.reason_code === "run_start_not_authorized" ? "La investigación no empezó" : "La investigación se detuvo";
    return { ...base, text, detail: `Causa: ${cause ?? "desconocida"}.`, tone: "critical" };
  }
  // Only a person retries; the agent continuing within a run is not a story entry.
  if (event.summary === "Investigation continued." && event.actor.type === "human") {
    return { ...base, text: "Reintentaste la investigación" };
  }
  if (event.summary.startsWith("Authorization denied")) {
    return { ...base, text: "Se denegó un permiso del agente", detail: capitalize(`${TERMINATED.denied}.`), tone: "critical" };
  }
  // The reasoning tells the hypothesis and the mitigation with their content.
  if (event.kind === "investigation_result" && reasoned && event.summary.includes("proposed a")) return null;
  const text = SUMMARIES[event.summary];
  if (!text) return null;
  return { ...base, text, tone: event.summary.endsWith("success.") ? "success" : undefined };
}

const VERDICT: Record<string, { label: string; tone: Tone }> = {
  supports: { label: "Respalda la hipótesis", tone: "success" },
  contradicts: { label: "Contradice la hipótesis", tone: "critical" },
  inconclusive: { label: "No concluyente", tone: "neutral" },
  empty: { label: "No encontró nada", tone: "warning" },
};

/** A recalled memory (#773) names the closed incident whose postmortem it came from. */
const MEMORY = /^\/v1\/incidents\/([^/]+)\/postmortem$/;

function evidenceEntry(item: Evidence, cited: Set<string>, service: string): StoryEntry {
  const base = { id: item.evidence_id, at: Date.parse(item.collected_at ?? ""), actor: "agent" as const };
  const memory = item.source === "incident_memory" ? MEMORY.exec(item.query ?? "") : null;
  if (memory) {
    return { ...base, text: "Recuerdo de incidente cerrado", source: "knowledge", link: { to: `/incidentes/${memory[1]}` }, detail: item.finding ?? undefined };
  }
  const [source, text]: [EvidenceSource, string] =
    item.tool === "query_prometheus"
      ? ["metrics", "Consultó las métricas"]
      : item.tool === "query_elasticsearch"
        ? ["logs", "Consultó los logs"]
        : item.source === "change-events"
          ? ["changes", `Revisó los cambios recientes de ${service}`]
          : item.tool === "bok.search"
            ? ["knowledge", "Buscó en la base de conocimiento"]
            : ["reasoning", "Reunió evidencia"];
  // The model judged evidence against the hypothesis that cites it; a query that found nothing
  // was measured, so it always shows (#707).
  const verdict = item.empty ? "empty" : item.verdict && cited.has(item.evidence_id) ? item.verdict : null;
  return {
    ...base,
    text,
    source,
    badge: verdict ? VERDICT[verdict] : undefined,
    detail: verdict && item.finding ? item.finding : undefined,
    query: item.query ? { tool: item.tool ?? item.source, text: item.query, window: item.time_window ?? "" } : undefined,
  };
}

const CHANGE: Record<ChangeEvent["kind"], string> = { deploy: "Despliegue", rollback: "Reversión", ci: "Integración continua" };

function changeEntry(change: ChangeEvent): StoryEntry {
  const failed = change.status === "failed";
  return {
    id: change.change_id,
    at: Date.parse(change.occurred_at),
    actor: "system",
    text: `${CHANGE[change.kind]} de ${change.service}${change.version ? ` ${change.version}` : ""}${failed ? " falló" : ""}`,
    detail: change.author ? `Por ${change.author}` : undefined,
    tone: failed ? "warning" : undefined,
    source: "changes",
    link: change.url?.startsWith("https://") ? { to: change.url, external: true } : undefined,
  };
}

export function buildStory(live: LiveIncident): StoryEntry[] {
  const reasoning = typeof live.reasoning === "object" ? live.reasoning : null;
  const service = live.detail?.alert?.service ?? "";
  const hypothesis = reasoning?.hypotheses.at(-1);
  const cited = new Set(hypothesis?.supporting_evidence ?? []);
  const entries: (StoryEntry | null)[] = [
    ...live.events.map((event) => eventEntry(event, reasoning !== null)),
    ...(reasoning?.evidence ?? []).map((item) => evidenceEntry(item, cited, service)),
    ...(reasoning?.hypotheses ?? []).map((item) => ({
      id: item.hypothesis_id,
      at: Date.parse(item.created_at ?? ""),
      actor: "agent" as const,
      text: "Propuso una hipótesis",
      detail: item.statement,
      badge: { label: CONFIDENCE[item.confidence]?.label ?? item.confidence, tone: "brand" as const },
    })),
    ...(Array.isArray(live.changes) ? live.changes.map(changeEntry) : []),
  ];
  const mitigation = reasoning?.mitigation_strategy;
  if (mitigation) {
    entries.push({
      id: "mitigation",
      at: Date.parse(mitigation.created_at ?? ""),
      actor: "agent",
      text: "Propuso una mitigación",
      detail: mitigation.description,
      badge: mitigation.risk ? RISK[mitigation.risk] : undefined,
    });
  }
  return entries
    .filter((entry): entry is StoryEntry => entry !== null && Number.isFinite(entry.at))
    .sort((a, b) => a.at - b.at);
}
