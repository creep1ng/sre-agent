/** The RC-2 inbox: the pending decision, the morning digest and last night's log. */
const inbox = {
  "headline.one": "Una",
  "headline.one.rest": "decisión te espera.",
  "headline.many": "{count}",
  "headline.many.rest": "decisiones te esperan.",
  "headline.none": "Nada te espera.",
  "decision.waiting": "esperando desde las {time}",
  "decision.open": "Revisar y decidir",
  "decision.escalate": "Midnight necesita tu permiso para seguir.",
  "coffee.lead": "Mientras te tomas el café,",
  "coffee.em": "mira esto",
  "coffee.recovered": "se recuperó.",
  "coffee.ended": "terminó su investigación sin proponer una acción.",
  "night.title": "Anoche",
  "night.incident": "Incidente abierto.",
  "night.deploy": "Deploy de",
  "night.rollback": "Rollback de",
  "night.ci": "CI de",
  "night.failed": "Falló.",
  "state.connect": "Conecta la API para ver tu bandeja.",
  "state.auth": "La API rechazó la clave.",
  "state.forbidden": "Tu clave no puede leer incidentes.",
  "state.error": "No pudimos leer tu bandeja. Se reintenta sola.",
  "state.loading": "Leyendo tu bandeja…",
  "state.action": "Conectar API",
};

export default inbox;

declare module "@/i18n" {
  interface Namespaces {
    inbox: typeof inbox;
  }
}
