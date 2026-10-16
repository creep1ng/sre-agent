// Spanish vocabulary of the incident views. States and their meaning follow workflow 1.0.0
// (agent/workflows/incident-response.yaml); event kinds follow the run-event contract
// (agent/schemas/run-event.schema.yaml). Values the console does not know are shown as received.
export const STATE_LABELS = Object.freeze({
  detected: "Detectado",
  triage: "En triage",
  dismissed: "Descartado",
  linked: "Vinculado",
  active: "Activo",
  investigating: "Investigando",
  mitigating: "Mitigando",
  verifying: "Verificando",
  resolved: "Resuelto",
  postmortem: "En postmortem",
  closed: "Cerrado",
});

export const STATE_DESCRIPTIONS = Object.freeze({
  detected: "Hay una alerta sin decisión todavía.",
  triage: "Se decide qué hacer con la alerta.",
  dismissed: "La alerta se descartó como ruido.",
  linked: "La alerta se asoció a un incidente existente.",
  active: "Incidente declarado; el war room está abierto.",
  investigating: "Se reúne evidencia y se formulan hipótesis.",
  mitigating: "Se propone, aprueba y aplica una mitigación.",
  verifying: "Se comprueba que el servicio quedó estable.",
  resolved: "El servicio está estable; falta el postmortem.",
  postmortem: "Se redacta y valida el postmortem.",
  closed: "La atención cerró con su postmortem.",
});

export const RUN_LABELS = Object.freeze({
  running: "Run en curso",
  awaiting_human: "Decisión pendiente",
  completed: "Run completado",
  terminated: "Run terminado",
});

// Tone: blue records the workflow's work, amber asks for or records a human decision,
// red is a block or an escalation, green closes the run.
export const EVENT_KINDS = Object.freeze({
  state_change: Object.freeze({ label: "Cambio de estado", tone: "info" }),
  evidence_collected: Object.freeze({ label: "Evidencia recogida", tone: "info" }),
  hypothesis_proposed: Object.freeze({ label: "Hipótesis propuesta", tone: "info" }),
  investigation_result: Object.freeze({ label: "Resultado de investigación", tone: "info" }),
  dispatch_receipt: Object.freeze({ label: "Despacho de investigación", tone: "info" }),
  mitigation_proposed: Object.freeze({ label: "Mitigación propuesta", tone: "warning" }),
  human_command: Object.freeze({ label: "Comando humano", tone: "warning" }),
  denial: Object.freeze({ label: "Denegado", tone: "critical" }),
  escalation: Object.freeze({ label: "Escalamiento", tone: "critical" }),
  run_terminated: Object.freeze({ label: "Run terminado", tone: "success" }),
});

export const ACTORS = Object.freeze({
  human: Object.freeze({ label: "Persona", icon: "icon-human" }),
  agent: Object.freeze({ label: "Agente", icon: "icon-agent" }),
  system: Object.freeze({ label: "Sistema", icon: "icon-system" }),
});

export function stateLabel(state) {
  if (typeof state !== "string" || state === "") return "—";
  return STATE_LABELS[state] ?? state;
}
