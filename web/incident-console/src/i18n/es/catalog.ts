/** The action catalog: what Midnight may run, who runs it and what it ran (#870). */
const catalog = {
  title: "Acciones",
  lead: "Las operaciones que Midnight puede ejecutar en tus servicios. Su agente ejecuta cada una solo después de que una persona la aprueba.",
  "blocked.unauthenticated": "Conecta una credencial",
  "blocked.loading": "Cargando el catálogo…",
  "blocked.auth": "La API rechazó la credencial",
  "blocked.forbidden": "Sin permiso para ver el catálogo",
  "blocked.error": "No pudimos leer el catálogo",
  "blocked.connect": "Conectar API",
  stale: "Sin conexión con la API",
  "executor.unavailable": "El ejecutor no responde: nada puede ejecutarse hasta que vuelva. Estas son las operaciones registradas.",
  "executor.not_configured": "Esta instalación no tiene ejecutor: nada puede ejecutarse.",
  empty: "No hay operaciones registradas.",
  "operation.deployment.rollback": "Volver a una versión anterior",
  "operation.deployment.restart": "Reiniciar en la versión actual",
  "service.one": "1 acción",
  "service.many": "{count} acciones",
  "service.last": "última ejecución {when}",
  "service.never": "sin ejecuciones",
  "operation.flag.set": "Apagar un flag de fallo",
  "runner.none": "Nadie puede ejecutarla: ningún permiso la cubre.",
  "parameters.unknown": "parámetros desconocidos",
  "parameters.unlisted": "valores no disponibles",
  executions: "Ejecuciones recientes ({count})",
  "executions.none": "Nunca se ha ejecutado.",
  "outcome.succeeded": "Se ejecutó",
  "outcome.refused": "Rechazada por falta de permiso",
  "outcome.failed": "No se ejecutó",
  "approved.by": "aprobó {name}",
  "approved.someone": "una persona",
  "incident.open": "Ver el incidente",
};

export default catalog;

declare module "@/i18n" {
  interface Namespaces {
    catalog: typeof catalog;
  }
}
