/** The scenario simulator (mock mode): the story it writes and the notices it raises. */
const simulator = {
  "event.detected": "Detectamos: {summary}",
  "event.declared": "Declaraste el incidente · {severity}",
  "event.investigating": "Empezó a investigar",
  "event.hypothesis": "Propuso una hipótesis con confianza {confidence}",
  "event.proposed": "Propuso: {summary}",
  "event.approved": "Aprobaste: {summary}",
  "event.rejected": "Rechazaste la propuesta",
  "event.changes": "Pediste cambios a la propuesta",
  "event.revising": "Está preparando una nueva propuesta",
  "event.linked": "Vinculaste la alerta «{title}»",
  "event.applied": "Aplicaste la mitigación",
  "event.watching": "Está vigilando la señal para confirmar la recuperación",
  "event.stable": "La señal se mantiene bajo el umbral",
  "event.stable.detail": "Recomienda confirmar la recuperación.",
  "event.confirmed": "Confirmaste que el servicio está estable",
  "event.notStable": "Indicaste que el servicio sigue fallando",
  "event.reinvestigating": "Volvió a investigar",
  "event.resolved": "Incidente resuelto en {duration}",
  "event.drafting": "Empezó a redactar el postmortem",
  "event.drafted": "Redactó el borrador del postmortem",
  "event.closed": "Aprobaste el postmortem y cerraste el incidente",
  "event.retried": "Reintentaste la investigación",
  "event.severity": "Cambiaste la gravedad a {severity}",
  "event.stopped": "El agente se detuvo: su identidad está desactivada",
  "confidence.low": "baja",
  "confidence.medium": "media",
  "confidence.high": "alta",
  "failure.title": "El agente no pudo empezar a investigar",
  "failure.reason": "Su identidad («incident-harness») está desactivada, así que el gateway rechazó la investigación.",
  "failure.fix": "Actívala en Administración → Identidades y vuelve a intentarlo.",
  "notice.alert": "Nueva alerta · {severity}",
  "notice.failed": "{id} · El agente no pudo investigar",
  "notice.failed.detail": "Su identidad está desactivada. Revisa el incidente para corregirlo.",
  "notice.stable": "{id} · El servicio parece estable",
  "notice.stable.detail": "El agente recomienda confirmar la recuperación.",
  "notice.proposal": "{id} · El agente propone una mitigación",
  "notice.postmortem": "{id} · Postmortem listo para revisar",
  "notice.postmortem.detail": "El agente lo redactó con la historia del incidente.",
  "action.view": "Ver",
  "action.review": "Revisar",
  "action.confirm": "Confirmar",
};

export default simulator;

declare module "@/i18n" {
  interface Namespaces {
    simulator: typeof simulator;
  }
}
