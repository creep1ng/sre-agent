import type { RunEvent } from "@/lib/incident-api";

/** Why an investigation dispatch ended, by `reason_code` (#705), as the war room says it. */
export const DISPATCH_CAUSES: Record<string, string> = {
  producer_interrupted: "la investigación se interrumpió antes de terminar",
  harness_not_configured: "no hay un modelo configurado para investigar",
  harness_identity_unavailable:
    "la identidad del investigador no está disponible; reactívala en Principales o pide ayuda a un administrador",
  mcp_discovery_denied: "no hay permiso para usar las herramientas de observabilidad",
  mcp_discovery_rejected: "las herramientas de observabilidad no están configuradas o rechazaron la conexión",
  mcp_discovery_transient: "las herramientas de observabilidad no respondieron",
  governed_call_denied: "se denegó una consulta del investigador",
  investigation_mcp_contract_rejected: "una consulta a una herramienta no cumplió su contrato",
  investigation_upstream_unavailable: "el proveedor del modelo no respondió",
  investigation_tool_unavailable: "una herramienta de observabilidad falló o no respondió a tiempo",
  investigation_max_steps: "se agotaron los pasos sin llegar a una conclusión",
  investigation_invalid_output: "el modelo respondió en un formato no válido",
  investigator_failed: "el investigador falló",
  result_persistence_uncertain: "no se pudo confirmar que el resultado se guardó",
  stale_incident_snapshot: "el incidente cambió mientras se investigaba",
};

export const TERMINATED: Record<string, string> = {
  denied: "se denegó un permiso del agente; un administrador debe concederlo antes de reintentar",
  max_steps: "se agotaron los pasos sin llegar a una conclusión",
  invalid_output: "el modelo respondió en un formato no válido",
  upstream_unavailable: "el proveedor del modelo o una herramienta no respondió",
  needs_human: "el agente necesita que una persona intervenga",
};

export function capitalize(text: string): string {
  return text ? `${text[0].toUpperCase()}${text.slice(1)}` : text;
}

/** The cause of the last run that stopped without finishing, in Spanish. */
export function endingCause(events: RunEvent[], terminatedReason: string | null): string {
  const code = events.findLast((event) => event.reason_code && DISPATCH_CAUSES[event.reason_code])?.reason_code;
  return capitalize(
    (code && DISPATCH_CAUSES[code]) ?? (terminatedReason && TERMINATED[terminatedReason]) ?? "la investigación no terminó",
  );
}
