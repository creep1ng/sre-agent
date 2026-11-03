/** The administration plane: identities, permissions, models and resources, consumption and audit. */
const admin = {
  "nav.identities": "Identidades",
  "nav.permissions": "Permisos",
  "nav.resources": "Modelos y recursos",
  "nav.consumption": "Consumo",
  "nav.audit": "Auditoría",

  "common.refresh": "Actualizar",
  "common.cancel": "Cancelar",
  "common.close": "Cerrar",
  "common.loading": "Cargando…",
  "common.notConfigured": "Sin configurar",
  "common.unavailable": "No disponible",
  "common.truncated": "La lista está truncada: hay más elementos.",
  "common.count": "{count} en total",
  "common.retry": "Reintentar",

  "status.active": "Activo",
  "status.inactive": "Inactivo",
  "status.revoked": "Revocado",
  "status.expired": "Vencido",
  "status.unknown": "Desconocido",
  "kind.human": "Persona",
  "kind.agent": "Agente",

  "gate.title": "Conecta una clave de administración para ver esta sección.",
  "gate.action": "Conectar con la API",

  "error.network": "No se pudo contactar la API.",
  "error.network.detail": "Revisa que el stack esté arriba y vuelve a intentar.",
  "error.auth": "La clave no es válida.",
  "error.auth.detail": "Conecta otra clave de API. No se confirmó nada más.",
  "error.forbidden": "Esta clave no tiene acceso.",
  "error.forbidden.detail": "La identidad conectada no puede ver ni cambiar esto. No se revela nada más.",
  "error.missing": "No existe o no es visible.",
  "error.missing.detail": "Vuelve a cargar la lista.",
  "error.conflict": "Alguien lo cambió antes que tú.",
  "error.conflict.detail": "Se muestra la versión actual; no se sobrescribió nada.",
  "error.invalid": "La API rechazó los datos.",
  "error.invalid.detail": "Revisa los campos. No se cambió nada.",
  "error.too_large": "El alcance es demasiado grande.",
  "error.too_large.detail": "Acota el filtro y vuelve a consultar.",
  "error.unavailable": "La API no respondió como se esperaba.",
  "error.unavailable.detail": "No se sustituye por un resultado vacío. Vuelve a intentar.",

  "type.llm_model": "Modelo LLM",
  "type.mcp_server": "Servidor MCP",
  "type.mcp_tool": "Herramienta MCP",
  "type.skill": "Skill",
  "type.bok_collection": "Colección BoK",
  "type.incident_workflow": "Flujo",
  "type.service_operation": "Operación de servicio",
  "type.administrative_control": "Control administrativo",

};

export default admin;

declare module "@/i18n" {
  interface Namespaces {
    admin: typeof admin;
  }
}
