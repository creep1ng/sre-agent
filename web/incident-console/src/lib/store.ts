/*
 * Mock backend of the console (mock mode). It follows agent/workflows/incident-response.yaml
 * (investigating → mitigating → verifying → resolved → postmortem → closed) and
 * simulates the agent with timed jobs, so the UI can be driven end to end.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { formatDuration } from "./format";
import { SCENARIOS, postmortemSteps } from "./scenarios";
import type {
  AgentJob,
  AgentStep,
  Alert,
  DecisionOutcome,
  Finding,
  Incident,
  JobKind,
  PostmortemDoc,
  ProposalDraftRef,
  ScenarioKey,
  Settings,
  Severity,
  TimelineEvent,
} from "./types";
import { SEVERITY, SOURCE_LABEL } from "./vocabulary";

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

/** After "Ya la apliqué": the signal starts to drop, then the agent judges it stable. */
const RECOVERY_DELAY_MS = 3 * SECOND;
const STABLE_AFTER_MS = 20 * SECOND;
const FAIL_AFTER_MS = 2400;
/** Agent events older than this when processed (e.g. after a reload) do not raise a toast. */
const TOAST_WINDOW_MS = 5 * SECOND;

/* ------------------------------------------------------------------ notices */

export interface Notice {
  title: string;
  description?: string;
  tone: "info" | "success" | "warning" | "error";
  href?: string;
  actionLabel?: string;
}

type NoticeListener = (notice: Notice) => void;
const listeners = new Set<NoticeListener>();

export function subscribeNotices(listener: NoticeListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(notice: Notice, at: number, now: number) {
  if (now - at > TOAST_WINDOW_MS) return;
  queueMicrotask(() => listeners.forEach((listener) => listener(notice)));
}

/* --------------------------------------------------------------------- ids */

function hex(length: number): string {
  const bytes = new Uint8Array(Math.ceil(length / 2));
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, length);
}

function eventId() {
  return `evt_${hex(12)}`;
}

function event(at: number, actor: TimelineEvent["actor"], text: string, extra: Partial<TimelineEvent> = {}) {
  return { id: eventId(), at, actor, text, ...extra } satisfies TimelineEvent;
}

/* ----------------------------------------------------------------- helpers */

function makeAlert(scenario: ScenarioKey, startedAt: number): Alert {
  const script = SCENARIOS[scenario];
  const draft = script.alert(startedAt);
  return {
    id: `alt-${draft.service}-${hex(12)}`,
    scenario,
    ...draft,
    startedAt,
    detectedAt: startedAt + script.detectionDelayMs,
    status: "new",
  };
}

function makeJob(
  kind: JobKind,
  ordinal: number,
  steps: AgentStep[],
  startedAt: number,
  extra: Partial<AgentJob> = {},
): AgentJob {
  return { kind, ordinal, startedAt, steps, done: 0, findings: [], ...extra };
}

function stepEnd(job: AgentJob, index: number): number {
  let total = job.startedAt;
  for (let i = 0; i <= index; i += 1) total += job.steps[i].durationMs;
  return total;
}

function toFinding(step: AgentStep, at: number): Finding | undefined {
  if (!step.finding) return undefined;
  return { ...step.finding, id: `ev_${hex(10)}`, at };
}

function primaryAlert(state: State, incident: Incident): Alert {
  const alert = state.alerts.find((a) => a.id === incident.alertIds[0]);
  if (!alert) throw new Error(`incident ${incident.id} has no alert`);
  return alert;
}

function confidenceLabel(confidence: "low" | "medium" | "high") {
  return { low: "baja", medium: "media", high: "alta" }[confidence];
}

/* ------------------------------------------------------- history (seeded) */

function closedIncident(scenario: ScenarioKey, number: number, startedAt: number) {
  const script = SCENARIOS[scenario];
  const alert = makeAlert(scenario, startedAt);
  const id = `INC-${number}`;
  const declaredAt = alert.detectedAt + 2 * MINUTE;
  const steps = script.investigation(alert);
  const findings = steps
    .map((step, index) => toFinding(step, declaredAt + (index + 1) * 25 * SECOND))
    .filter((finding): finding is Finding => Boolean(finding));
  const proposedAt = declaredAt + 2 * MINUTE + 10 * SECOND;
  const approvedAt = proposedAt + 90 * SECOND;
  const appliedAt = approvedAt + 2 * MINUTE;
  const confirmedAt = appliedAt + 4 * MINUTE;
  const draftedAt = confirmedAt + MINUTE;
  const closedAt = draftedAt + 6 * MINUTE;
  const hypothesis = script.hypothesis(alert);
  const draft = script.proposal(alert);

  alert.status = "declared";
  alert.incidentId = id;
  alert.recoveryStartAt = appliedAt + 30 * SECOND;

  const incident: Incident = {
    id,
    number,
    backendId: `inc-${hex(32)}`,
    title: alert.title,
    service: alert.service,
    severity: alert.severity,
    impact: alert.suggestedImpact,
    scenario,
    alertIds: [alert.id],
    declaredAt,
    state: "closed",
    investigations: 1,
    proposals: [
      {
        id: `mit_${hex(10)}`,
        number: 1,
        createdAt: proposedAt,
        hypothesis,
        findings,
        ...draft,
        decision: { outcome: "approved", at: approvedAt },
      },
    ],
    verification: { checklist: draft.steps.map(() => true), appliedAt, stableSuggestedAt: confirmedAt - MINUTE, confirmedAt },
    events: [
      event(alert.detectedAt, "system", `Detectamos: ${alert.summary}`, { kind: "milestone" }),
      event(declaredAt, "you", `Declaraste el incidente · ${SEVERITY[alert.severity].short}`, {
        detail: alert.suggestedImpact,
        kind: "milestone",
      }),
      event(declaredAt, "agent", "Empezó a investigar", { kind: "milestone" }),
      ...findings.map((finding) =>
        event(finding.at, "agent", finding.title, { detail: SOURCE_LABEL[finding.source], kind: "finding" }),
      ),
      event(proposedAt, "agent", `Propuso una hipótesis con confianza ${confidenceLabel(hypothesis.confidence)}`, {
        detail: hypothesis.statement,
        kind: "milestone",
      }),
      event(proposedAt, "agent", `Propuso: ${draft.summary}`, { kind: "milestone" }),
      event(approvedAt, "you", `Aprobaste: ${draft.summary}`, { kind: "milestone" }),
      event(appliedAt, "you", "Aplicaste la mitigación", { kind: "milestone" }),
      event(confirmedAt, "you", "Confirmaste que el servicio está estable", { kind: "milestone", tone: "success" }),
      event(confirmedAt, "system", `Incidente resuelto en ${formatDuration(confirmedAt - alert.startedAt)}`, {
        kind: "milestone",
        tone: "success",
      }),
      event(draftedAt, "agent", "Redactó el borrador del postmortem", { kind: "milestone" }),
      event(closedAt, "you", "Aprobaste el postmortem y cerraste el incidente", { kind: "milestone", tone: "success" }),
    ],
    resolvedAt: confirmedAt,
    closedAt,
    runIds: [`run_${hex(16)}`, `run_${hex(16)}`],
  };
  incident.postmortem = {
    status: "approved",
    doc: script.postmortem(incident, alert, closedAt),
    draftedAt,
    approvedAt: closedAt,
  };
  return { alert, incident };
}

function seed(now: number) {
  const images = closedIncident("images", 10, now - 3 * 24 * HOUR - 2 * HOUR);
  const cart = closedIncident("cart", 11, now - 26 * HOUR);
  return {
    alerts: [
      makeAlert("payments", now - 3 * MINUTE - 10 * SECOND),
      makeAlert("recommendations", now - 26 * MINUTE),
      makeAlert("ads", now - 21 * MINUTE),
      images.alert,
      cart.alert,
    ],
    incidents: [cart.incident, images.incident],
    nextNumber: 12,
    settings: { agentFailure: false } satisfies Settings,
    seededAt: now,
  };
}

/* -------------------------------------------------------------------- store */

interface Data {
  alerts: Alert[];
  incidents: Incident[];
  nextNumber: number;
  settings: Settings;
  seededAt: number;
}

interface Actions {
  declare: (alertId: string, input: { severity: Severity; impact: string }) => string | undefined;
  dismiss: (alertId: string, reason: string) => void;
  restore: (alertId: string) => void;
  link: (alertId: string, incidentId: string) => void;
  decide: (incidentId: string, outcome: DecisionOutcome, comment?: string) => void;
  toggleStep: (incidentId: string, index: number) => void;
  markApplied: (incidentId: string) => void;
  confirmStable: (incidentId: string) => void;
  reportNotStable: (incidentId: string) => void;
  retryAgent: (incidentId: string) => void;
  editPostmortem: (incidentId: string, patch: Partial<PostmortemDoc>) => void;
  approveAndClose: (incidentId: string) => void;
  addNote: (incidentId: string, text: string) => void;
  changeSeverity: (incidentId: string, severity: Severity) => void;
  spawnAlert: (scenario: ScenarioKey) => boolean;
  setAgentFailure: (value: boolean) => void;
  reset: () => void;
  tick: (now: number) => void;
}

export type State = Data & Actions;

function updateIncident(state: State, incidentId: string, update: (incident: Incident) => Incident): Partial<State> {
  return {
    incidents: state.incidents.map((incident) => (incident.id === incidentId ? update(incident) : incident)),
  };
}

export const useStore = create<State>()(
  persist(
    (set, get) => ({
      ...seed(Date.now()),

      declare: (alertId, { severity, impact }) => {
        const state = get();
        const alert = state.alerts.find((a) => a.id === alertId);
        if (!alert || alert.status !== "new") return undefined;
        const now = Date.now();
        const number = state.nextNumber;
        const id = `INC-${number}`;
        const script = SCENARIOS[alert.scenario];
        const incident: Incident = {
          id,
          number,
          backendId: `inc-${hex(32)}`,
          title: alert.title,
          service: alert.service,
          severity,
          impact: impact.trim() || alert.suggestedImpact,
          scenario: alert.scenario,
          alertIds: [alert.id],
          declaredAt: now,
          state: "investigating",
          investigations: 1,
          job: makeJob("investigation", 1, script.investigation(alert), now, {
            failAfterMs: state.settings.agentFailure ? FAIL_AFTER_MS : undefined,
          }),
          proposals: [],
          events: [
            event(alert.detectedAt, "system", `Detectamos: ${alert.summary}`, { kind: "milestone" }),
            event(now, "you", `Declaraste el incidente · ${SEVERITY[severity].short}`, {
              detail: impact.trim() || alert.suggestedImpact,
              kind: "milestone",
            }),
            event(now, "agent", "Empezó a investigar", { kind: "milestone" }),
          ],
          runIds: [`run_${hex(16)}`],
        };
        set({
          nextNumber: number + 1,
          incidents: [incident, ...state.incidents],
          alerts: state.alerts.map((a) => (a.id === alertId ? { ...a, status: "declared", incidentId: id } : a)),
        });
        return id;
      },

      dismiss: (alertId, reason) =>
        set((state) => ({
          alerts: state.alerts.map((a) =>
            a.id === alertId ? { ...a, status: "dismissed", dismissReason: reason, dismissedAt: Date.now() } : a,
          ),
        })),

      restore: (alertId) =>
        set((state) => ({
          alerts: state.alerts.map((a) =>
            a.id === alertId ? { ...a, status: "new", dismissReason: undefined, dismissedAt: undefined } : a,
          ),
        })),

      link: (alertId, incidentId) =>
        set((state) => {
          const alert = state.alerts.find((a) => a.id === alertId);
          if (!alert) return {};
          const now = Date.now();
          return {
            alerts: state.alerts.map((a) => (a.id === alertId ? { ...a, status: "linked", incidentId } : a)),
            ...updateIncident(state, incidentId, (incident) => ({
              ...incident,
              alertIds: [...incident.alertIds, alertId],
              events: [
                ...incident.events,
                event(now, "you", `Vinculaste la alerta «${alert.title}»`, { detail: alert.summary, kind: "milestone" }),
              ],
            })),
          };
        }),

      decide: (incidentId, outcome, comment) =>
        set((state) => {
          const now = Date.now();
          return updateIncident(state, incidentId, (incident) => {
            const current = incident.proposals.at(-1);
            if (incident.state !== "mitigating" || !current) return incident;
            const note = comment?.trim() || undefined;
            const proposals = incident.proposals.map((p) =>
              p.id === current.id ? { ...p, decision: { outcome, comment: note, at: now } } : p,
            );
            if (outcome === "approved") {
              return {
                ...incident,
                proposals,
                state: "verifying",
                verification: { checklist: current.steps.map(() => false) },
                events: [
                  ...incident.events,
                  event(now, "you", `Aprobaste: ${current.summary}`, { detail: note, kind: "milestone" }),
                ],
              };
            }
            const alert = primaryAlert(state, incident);
            const revision = SCENARIOS[incident.scenario].revision(alert, note);
            return {
              ...incident,
              proposals,
              state: "investigating",
              investigations: incident.investigations + 1,
              job: makeJob("revision", incident.investigations + 1, revision.steps, now, { draft: revision.proposal }),
              runIds: [...incident.runIds, `run_${hex(16)}`],
              events: [
                ...incident.events,
                event(
                  now,
                  "you",
                  outcome === "rejected" ? "Rechazaste la propuesta" : "Pediste cambios a la propuesta",
                  { detail: note, kind: "milestone", tone: "warning" },
                ),
                event(now, "agent", "Está preparando una nueva propuesta"),
              ],
            };
          });
        }),

      toggleStep: (incidentId, index) =>
        set((state) =>
          updateIncident(state, incidentId, (incident) => {
            if (!incident.verification) return incident;
            const checklist = incident.verification.checklist.map((value, i) => (i === index ? !value : value));
            return { ...incident, verification: { ...incident.verification, checklist } };
          }),
        ),

      markApplied: (incidentId) =>
        set((state) => {
          const incident = state.incidents.find((i) => i.id === incidentId);
          if (!incident || incident.state !== "verifying" || incident.verification?.appliedAt) return {};
          const now = Date.now();
          return {
            alerts: state.alerts.map((a) =>
              incident.alertIds.includes(a.id) ? { ...a, recoveryStartAt: now + RECOVERY_DELAY_MS } : a,
            ),
            ...updateIncident(state, incidentId, (current) => ({
              ...current,
              verification: {
                checklist: current.verification?.checklist ?? [],
                appliedAt: now,
              },
              events: [
                ...current.events,
                event(now, "you", "Aplicaste la mitigación", { kind: "milestone" }),
                event(now, "agent", "Está vigilando la señal para confirmar la recuperación"),
              ],
            })),
          };
        }),

      confirmStable: (incidentId) =>
        set((state) => {
          const now = Date.now();
          return updateIncident(state, incidentId, (incident) => {
            if (incident.state !== "verifying") return incident;
            const alert = primaryAlert(state, incident);
            return {
              ...incident,
              state: "postmortem",
              resolvedAt: now,
              verification: { checklist: [], ...incident.verification, confirmedAt: now },
              postmortem: { status: "drafting" },
              job: makeJob("postmortem", incident.investigations, postmortemSteps(), now),
              runIds: [...incident.runIds, `run_${hex(16)}`],
              events: [
                ...incident.events,
                event(now, "you", "Confirmaste que el servicio está estable", { kind: "milestone", tone: "success" }),
                event(now, "system", `Incidente resuelto en ${formatDuration(now - alert.startedAt)}`, {
                  kind: "milestone",
                  tone: "success",
                }),
                event(now, "agent", "Empezó a redactar el postmortem"),
              ],
            };
          });
        }),

      reportNotStable: (incidentId) =>
        set((state) => {
          const incident = state.incidents.find((i) => i.id === incidentId);
          if (!incident || incident.state !== "verifying") return {};
          const now = Date.now();
          const alert = primaryAlert(state, incident);
          const next = SCENARIOS[incident.scenario].reinvestigation(alert);
          return {
            alerts: state.alerts.map((a) =>
              incident.alertIds.includes(a.id) ? { ...a, recoveryStartAt: undefined } : a,
            ),
            ...updateIncident(state, incidentId, (current) => ({
              ...current,
              state: "investigating",
              verification: undefined,
              investigations: current.investigations + 1,
              job: makeJob("reinvestigation", current.investigations + 1, next.steps, now, { draft: next.proposal }),
              runIds: [...current.runIds, `run_${hex(16)}`],
              events: [
                ...current.events,
                event(now, "you", "Indicaste que el servicio sigue fallando", { kind: "milestone", tone: "warning" }),
                event(now, "agent", "Volvió a investigar", { kind: "milestone" }),
              ],
            })),
          };
        }),

      retryAgent: (incidentId) =>
        set((state) => {
          const now = Date.now();
          return updateIncident(state, incidentId, (incident) => {
            const job = incident.job;
            if (!job?.failure) return incident;
            return {
              ...incident,
              job: { ...job, startedAt: now, done: 0, findings: [], failure: undefined, failAfterMs: undefined },
              runIds: [...incident.runIds, `run_${hex(16)}`],
              events: [
                ...incident.events,
                event(now, "you", "Reintentaste la investigación"),
                event(now, "agent", "Empezó a investigar", { kind: "milestone" }),
              ],
            };
          });
        }),

      editPostmortem: (incidentId, patch) =>
        set((state) =>
          updateIncident(state, incidentId, (incident) => {
            const postmortem = incident.postmortem;
            if (!postmortem?.doc || postmortem.status !== "review") return incident;
            return {
              ...incident,
              postmortem: { ...postmortem, doc: { ...postmortem.doc, ...patch }, editedAt: Date.now() },
            };
          }),
        ),

      approveAndClose: (incidentId) =>
        set((state) => {
          const now = Date.now();
          return updateIncident(state, incidentId, (incident) => {
            if (incident.state !== "postmortem" || incident.postmortem?.status !== "review") return incident;
            return {
              ...incident,
              state: "closed",
              closedAt: now,
              postmortem: { ...incident.postmortem, status: "approved", approvedAt: now },
              events: [
                ...incident.events,
                event(now, "you", "Aprobaste el postmortem y cerraste el incidente", {
                  kind: "milestone",
                  tone: "success",
                }),
              ],
            };
          });
        }),

      addNote: (incidentId, text) =>
        set((state) =>
          updateIncident(state, incidentId, (incident) => ({
            ...incident,
            events: [...incident.events, event(Date.now(), "you", text.trim(), { kind: "note" })],
          })),
        ),

      changeSeverity: (incidentId, severity) =>
        set((state) =>
          updateIncident(state, incidentId, (incident) =>
            incident.severity === severity
              ? incident
              : {
                  ...incident,
                  severity,
                  events: [
                    ...incident.events,
                    event(Date.now(), "you", `Cambiaste la gravedad a ${SEVERITY[severity].short}`, {
                      kind: "milestone",
                    }),
                  ],
                },
          ),
        ),

      spawnAlert: (scenario) => {
        const state = get();
        if (state.alerts.some((a) => a.scenario === scenario && a.status === "new")) return false;
        const active = state.incidents.find((i) => i.scenario === scenario && i.state !== "closed");
        if (active) return false;
        const now = Date.now();
        const alert = makeAlert(scenario, now - SCENARIOS[scenario].detectionDelayMs);
        set({ alerts: [alert, ...state.alerts] });
        notify(
          {
            title: `Nueva alerta · ${SEVERITY[alert.severity].short}`,
            description: alert.title,
            tone: alert.severity === "sev1" ? "error" : "warning",
            href: "/",
            actionLabel: "Ver",
          },
          now,
          now,
        );
        return true;
      },

      setAgentFailure: (value) => set((state) => ({ settings: { ...state.settings, agentFailure: value } })),

      reset: () => set(seed(Date.now())),

      tick: (now) => {
        const state = get();
        let changed = false;
        const incidents = state.incidents.map((incident) => {
          const next = advance(state, incident, now);
          if (next !== incident) changed = true;
          return next;
        });
        if (changed) set({ incidents });
      },
    }),
    {
      name: "midnight-incident-console-v1",
      version: 1,
      partialize: (state) => ({
        alerts: state.alerts,
        incidents: state.incidents,
        nextNumber: state.nextNumber,
        settings: state.settings,
        seededAt: state.seededAt,
      }),
    },
  ),
);

/* --------------------------------------------------------------- simulator */

function advance(state: State, incident: Incident, now: number): Incident {
  let current = incident;

  if (current.job && !current.job.failure) {
    const job = current.job;
    if (job.failAfterMs !== undefined && now >= job.startedAt + job.failAfterMs) {
      const at = job.startedAt + job.failAfterMs;
      notify(
        {
          title: `${current.id} · El agente no pudo investigar`,
          description: "Su identidad está desactivada. Revisa el incidente para corregirlo.",
          tone: "error",
          href: `/incidentes/${current.id}`,
          actionLabel: "Ver",
        },
        at,
        now,
      );
      return {
        ...current,
        job: {
          ...job,
          failure: {
            title: "El agente no pudo empezar a investigar",
            reason: "Su identidad («incident-harness») está desactivada, así que el gateway rechazó la investigación.",
            fix: "Actívala en Gobierno de IA → Principals y vuelve a intentarlo.",
            at,
          },
        },
        events: [
          ...current.events,
          event(at, "system", "El agente se detuvo: su identidad está desactivada", {
            kind: "milestone",
            tone: "critical",
          }),
        ],
      };
    }

    let done = job.done;
    const findings = [...job.findings];
    const events = [...current.events];
    while (done < job.steps.length && now >= stepEnd(job, done)) {
      const at = stepEnd(job, done);
      const finding = toFinding(job.steps[done], at);
      if (finding) {
        findings.push(finding);
        events.push(event(at, "agent", finding.title, { detail: SOURCE_LABEL[finding.source], kind: "finding" }));
      }
      done += 1;
    }
    if (done !== job.done) {
      current = { ...current, job: { ...job, done, findings }, events };
    }
    if (done === job.steps.length && current.job) {
      current = finishJob(state, current, current.job, stepEnd(current.job, done - 1), now);
    }
  }

  const verification = current.verification;
  if (
    current.state === "verifying" &&
    verification?.appliedAt &&
    !verification.stableSuggestedAt &&
    now >= verification.appliedAt + STABLE_AFTER_MS
  ) {
    const at = verification.appliedAt + STABLE_AFTER_MS;
    notify(
      {
        title: `${current.id} · El servicio parece estable`,
        description: "El agente recomienda confirmar la recuperación.",
        tone: "success",
        href: `/incidentes/${current.id}`,
        actionLabel: "Confirmar",
      },
      at,
      now,
    );
    current = {
      ...current,
      verification: { ...verification, stableSuggestedAt: at },
      events: [
        ...current.events,
        event(at, "agent", "La señal se mantiene bajo el umbral", {
          detail: "Recomienda confirmar la recuperación.",
          kind: "milestone",
        }),
      ],
    };
  }
  return current;
}

function finishJob(state: State, incident: Incident, job: AgentJob, at: number, now: number): Incident {
  const alert = primaryAlert(state, incident);
  const script = SCENARIOS[incident.scenario];

  if (job.kind === "postmortem") {
    notify(
      {
        title: `${incident.id} · Postmortem listo para revisar`,
        description: "El agente lo redactó con la historia del incidente.",
        tone: "info",
        href: `/incidentes/${incident.id}`,
        actionLabel: "Revisar",
      },
      at,
      now,
    );
    const withEvent: Incident = {
      ...incident,
      job: undefined,
      events: [...incident.events, event(at, "agent", "Redactó el borrador del postmortem", { kind: "milestone" })],
    };
    return {
      ...withEvent,
      postmortem: { status: "review", doc: script.postmortem(withEvent, alert, now), draftedAt: at },
    };
  }

  const previous = incident.proposals.at(-1);
  const hypothesis = previous?.hypothesis ?? script.hypothesis(alert);
  const draft: ProposalDraftRef = job.draft ?? script.proposal(alert);
  const findings = [...(previous?.findings ?? []), ...job.findings];
  const number = incident.proposals.length + 1;
  notify(
    {
      title: `${incident.id} · El agente propone una mitigación`,
      description: draft.summary,
      tone: "warning",
      href: `/incidentes/${incident.id}`,
      actionLabel: "Revisar",
    },
    at,
    now,
  );
  const events = [...incident.events];
  if (!previous) {
    events.push(
      event(at, "agent", `Propuso una hipótesis con confianza ${confidenceLabel(hypothesis.confidence)}`, {
        detail: hypothesis.statement,
        kind: "milestone",
      }),
    );
  }
  events.push(event(at, "agent", `Propuso: ${draft.summary}`, { kind: "milestone" }));
  return {
    ...incident,
    state: "mitigating",
    job: undefined,
    proposals: [
      ...incident.proposals,
      { id: `mit_${hex(10)}`, number, createdAt: at, hypothesis, findings, ...draft },
    ],
    events,
  };
}

/* ---------------------------------------------------------------- selectors */

export function alertsOf(state: Pick<State, "alerts">, incident: Incident): Alert[] {
  return incident.alertIds
    .map((id) => state.alerts.find((alert) => alert.id === id))
    .filter((alert): alert is Alert => Boolean(alert));
}
