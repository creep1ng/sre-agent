/** The console chrome: sidebar, mobile header and account menu. */
const shell = {
  "nav.main": "Principal",
  "nav.inbox": "Bandeja",
  "nav.incidents": "Incidentes",
  "nav.admin": "Administración",
  "nav.governance": "Gobierno de IA",
  "nav.sections": "Secciones de la consola",
  "nav.title": "Navegación",
  "nav.fold": "Plegar navegación",
  "nav.unfold": "Desplegar navegación",
  "nav.open": "Abrir menú",
  "search.open": "Buscar o ir a…",
  "search.label": "Buscar",
  "command.description": "Busca incidentes, alertas o acciones",
  "command.placeholder": "Busca un incidente, una alerta o una acción…",
  "command.empty": "No encontramos nada con ese texto.",
  "command.goTo": "Ir a",
  "agent.name": "Agente de incidentes",
  "agent.idle": "Disponible",
  "agent.stopped": "Detenido · {id}",
  "account.apiSession": "Sesión de API",
  "account.connected": "Conectada",
  "account.disconnected": "Sin conectar",
  "account.active": "Sesión activa",
  "account.theme": "Tema",
  "account.language": "Idioma",
  "theme.system": "Sistema",
  "theme.light": "Claro",
  "theme.dark": "Oscuro",
  "account.connect": "Conectar API",
  "account.disconnect": "Desconectar",
  "account.disconnected.toast": "Credencial desconectada",
};

export default shell;

declare module "@/i18n" {
  interface Namespaces {
    shell: typeof shell;
  }
}
