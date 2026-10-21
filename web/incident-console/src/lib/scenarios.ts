/*
 * Mock scripts for the OpenTelemetry demo store. Each scenario mirrors a real failure
 * flag of the store (flagd) and the evidence the governed MCP tools return for it.
 * The texts show the target quality: Spanish, human, no ids.
 */
import { formatDuration, formatTime } from "./format";
import type {
  AgentStep,
  Alert,
  Hypothesis,
  Incident,
  PostmortemDoc,
  Proposal,
  ProposalDraftRef,
  ScenarioKey,
  Severity,
  SignalSpec,
} from "./types";

export type ProposalDraft = ProposalDraftRef;

export interface AlertDraft {
  title: string;
  summary: string;
  service: string;
  severity: Severity;
  signal: SignalSpec;
  rule: string;
  source: string;
  suggestedImpact: string;
}

export interface Scenario {
  key: ScenarioKey;
  /** Time between the flag change and the rule firing. */
  detectionDelayMs: number;
  alert: (startedAt: number) => AlertDraft;
  investigation: (alert: Alert) => AgentStep[];
  hypothesis: (alert: Alert) => Hypothesis;
  proposal: (alert: Alert) => ProposalDraft;
  revision: (alert: Alert, comment: string | undefined) => { steps: AgentStep[]; proposal: ProposalDraft };
  reinvestigation: (alert: Alert) => { steps: AgentStep[]; proposal: ProposalDraft };
  postmortem: (incident: Incident, alert: Alert, now: number) => PostmortemDoc;
}

const t = formatTime;
const SECOND = 1000;

const POSTMORTEM_STEPS: AgentStep[] = [
  { label: "Reuniendo la historia del incidente", source: "reasoning", durationMs: 2600 },
  { label: "Resumiendo el impacto y la causa", source: "reasoning", durationMs: 2800 },
  { label: "Redactando acciones y pendientes", source: "reasoning", durationMs: 2400 },
];

export function postmortemSteps(): AgentStep[] {
  return POSTMORTEM_STEPS.map((step) => ({ ...step }));
}

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** "La mitigación fue desactivar el flag «x»." without nesting quotes. */
function mitigationSentence(proposal: Proposal | undefined): string {
  return proposal ? `La mitigación fue ${lowerFirst(proposal.summary)}` : "Se aplicó la mitigación";
}

function approvedProposal(incident: Incident): Proposal | undefined {
  return [...incident.proposals].reverse().find((p) => p.decision?.outcome === "approved");
}

/** Shared narrative pieces of every postmortem, built from what really happened. */
function narrative(incident: Incident, alert: Alert, now: number) {
  const approved = approvedProposal(incident);
  const resolvedAt = incident.resolvedAt ?? now;
  const duration = formatDuration(resolvedAt - alert.startedAt);
  const actions: string[] = [
    `${t(incident.declaredAt)} · Declaraste el incidente (${incident.severity.toUpperCase()}).`,
  ];
  for (const proposal of incident.proposals) {
    const decision = proposal.decision;
    if (!decision) continue;
    if (decision.outcome === "approved") {
      actions.push(`${t(decision.at)} · Aprobaste: ${lowerFirst(proposal.summary)}.`);
    } else if (decision.outcome === "changes_requested") {
      actions.push(`${t(decision.at)} · Pediste cambios a la propuesta: ${lowerFirst(proposal.summary)}.`);
    } else {
      actions.push(`${t(decision.at)} · Rechazaste la propuesta: ${lowerFirst(proposal.summary)}.`);
    }
  }
  if (incident.verification?.appliedAt) {
    actions.push(`${t(incident.verification.appliedAt)} · Aplicaste la mitigación.`);
  }
  if (incident.verification?.confirmedAt) {
    actions.push(`${t(incident.verification.confirmedAt)} · Confirmaste que el servicio está estable.`);
  }
  const timeline = incident.events
    .filter((event) => event.kind === "milestone")
    .map((event) => ({ at: event.at, text: event.text }));
  return { approved, resolvedAt, duration, actions, timeline };
}

/* ------------------------------------------------------------------ payments */

const payments: Scenario = {
  key: "payments",
  detectionDelayMs: 55 * SECOND,
  alert: (startedAt) => ({
    title: "Pagos fallando en checkout",
    summary: `El 100 % de los cobros falla desde las ${t(startedAt)} (umbral: 5 %).`,
    service: "checkout",
    severity: "sev1",
    signal: { label: "Cobros con error", unit: "%", threshold: 5, baseline: 0.3, peak: 100, max: 100 },
    rule: "Más del 5 % de los cobros con error durante 2 minutos",
    source: "Tienda OTel · métricas de Prometheus",
    suggestedImpact: "Los clientes no pueden pagar sus pedidos: «Place Order» falla.",
  }),
  investigation: (alert) => [
    {
      label: "Midiendo la tasa de errores de los cobros",
      source: "metrics",
      durationMs: 3800,
      finding: {
        source: "metrics",
        title: "El 100 % de los cobros falla",
        detail: `Desde las ${t(alert.startedAt)} todas las llamadas de checkout a PaymentService/Charge terminan en error. Antes era 0,3 %.`,
        verdict: "supports",
        query: {
          tool: "Prometheus · webstore-metrics",
          window: "Últimos 15 min",
          text: 'sum(rate(traces_span_metrics_calls_total{service_name="checkout", span_name="oteldemo.PaymentService/Charge", status_code="STATUS_CODE_ERROR"}[2m]))\n  / sum(rate(traces_span_metrics_calls_total{service_name="checkout", span_name="oteldemo.PaymentService/Charge"}[2m]))',
        },
      },
    },
    {
      label: "Buscando el error exacto en los logs de checkout",
      source: "logs",
      durationMs: 4600,
      finding: {
        source: "logs",
        title: "1.284 errores «Unavailable» en checkout",
        detail:
          "Todos dicen lo mismo: «could not charge the card: rpc error: code = Unavailable desc = dns: lookup badAddress: no such host».",
        verdict: "supports",
        query: {
          tool: "Elasticsearch · webstore-logs",
          window: "Últimos 15 min",
          text: 'resource.service.name:"checkout" AND severity_text:"ERROR"',
        },
      },
    },
    {
      label: "Revisando si el servicio de pagos está sano",
      source: "metrics",
      durationMs: 4200,
      finding: {
        source: "metrics",
        title: "El servicio de pagos está sano, pero no recibe cobros",
        detail: `payment no registra llamadas desde las ${t(alert.startedAt)}, responde a los chequeos de salud y no se ha reiniciado: el fallo ocurre antes de llegar a él.`,
        verdict: "supports",
        query: {
          tool: "Prometheus · webstore-metrics",
          window: "Últimos 15 min",
          text: 'sum(rate(traces_span_metrics_calls_total{service_name="payment", span_name="oteldemo.PaymentService/Charge"}[2m]))',
        },
      },
    },
    {
      label: "Buscando cambios recientes: despliegues y feature flags",
      source: "changes",
      durationMs: 4400,
      finding: {
        source: "changes",
        title: `Se activó el flag «paymentUnreachable» a las ${t(alert.startedAt - 20 * SECOND)}`,
        detail:
          "No hubo despliegues en las últimas 24 h. El único cambio es este flag, que hace que checkout envíe los cobros a una dirección que no existe.",
        verdict: "supports",
        query: { tool: "flagd · demo.flagd.json", window: "Últimas 24 h", text: 'paymentUnreachable: "off" → "on"' },
      },
    },
    {
      label: "Consultando la base de conocimiento",
      source: "knowledge",
      durationMs: 3600,
      finding: {
        source: "knowledge",
        title: "Runbook «Tienda OTel: fallas de pago»",
        detail:
          "Con «paymentUnreachable» activo, checkout usa la dirección badAddress:50051 y todos los cobros fallan. Se corrige desactivando el flag.",
        verdict: "context",
        query: {
          tool: "Base de conocimiento · otel-demo-runbooks",
          window: "—",
          text: "checkout PaymentService Unavailable badAddress",
        },
      },
    },
    { label: "Formulando la hipótesis y la mitigación", source: "reasoning", durationMs: 3000 },
  ],
  hypothesis: (alert) => ({
    statement: `Checkout no logra conectarse con el servicio de pagos: el flag «paymentUnreachable», activado a las ${t(alert.startedAt - 20 * SECOND)}, lo hace llamar a una dirección que no existe (badAddress:50051). Por eso falla el 100 % de los cobros aunque el servicio de pagos está sano.`,
    confidence: "high",
    refutedIf: "Si los cobros siguen fallando con el flag desactivado, la causa es otra.",
  }),
  proposal: () => ({
    summary: "Desactivar el flag «paymentUnreachable»",
    steps: [
      "Abre el panel de feature flags de la tienda (/feature).",
      "Cambia «paymentUnreachable» a off y guarda.",
      "Haz un pedido de prueba: debe completarse.",
      "Confirma que los cobros con error bajan del 5 %.",
    ],
    risk: "low",
    riskNote: "Se revierte en segundos y no requiere despliegue.",
    verification: "Los cobros con error bajan del 5 % y se mantienen así; un pedido de prueba se completa.",
  }),
  revision: (_alert, comment) => ({
    steps: [
      { label: "Leyendo tu comentario", source: "reasoning", durationMs: 2500 },
      {
        label: "Buscando una alternativa",
        source: "changes",
        durationMs: 3500,
        finding: {
          source: "changes",
          title: "La configuración base de flags no tiene fallas activas",
          detail: "Restaurarla desactiva «paymentUnreachable» y cualquier otro flag de prueba que esté encendido.",
          verdict: "context",
          query: { tool: "flagd · demo.flagd.json", window: "Configuración base", text: "flag_baseline" },
        },
      },
      { label: "Redactando una nueva propuesta", source: "reasoning", durationMs: 2500 },
    ],
    proposal: {
      summary: "Restaurar todos los flags a su configuración base",
      steps: [
        "Ejecuta el restablecimiento de flags de la tienda (otel_ec2.py reset).",
        "Espera unos 15 s a que flagd recargue la configuración.",
        "Haz un pedido de prueba: debe completarse.",
        "Confirma que los cobros con error bajan del 5 %.",
      ],
      risk: "low",
      riskNote: "También apaga otros flags de prueba que estuvieran activos.",
      verification: "Los cobros con error bajan del 5 % y se mantienen así; un pedido de prueba se completa.",
      revisionNote: comment
        ? `Ajustada según tu comentario: «${comment}»`
        : "Alternativa después de que rechazaras la propuesta anterior.",
    },
  }),
  reinvestigation: () => ({
    steps: [
      {
        label: "Midiendo de nuevo la tasa de errores",
        source: "metrics",
        durationMs: 3200,
        finding: {
          source: "metrics",
          title: "Los cobros siguen fallando",
          detail: "La tasa de error no bajó después del cambio.",
          verdict: "supports",
        },
      },
      {
        label: "Verificando el estado del flag",
        source: "changes",
        durationMs: 3400,
        finding: {
          source: "changes",
          title: "«paymentUnreachable» sigue activo",
          detail: "flagd todavía entrega el valor on: el cambio no se guardó o no se recargó.",
          verdict: "supports",
          query: { tool: "flagd · demo.flagd.json", window: "Ahora", text: 'paymentUnreachable: "on"' },
        },
      },
      { label: "Redactando una nueva propuesta", source: "reasoning", durationMs: 2400 },
    ],
    proposal: {
      summary: "Desactivar el flag y comprobar que quedó guardado",
      steps: [
        "Abre /feature y cambia «paymentUnreachable» a off.",
        "Pulsa «Save» y recarga la página: el flag debe seguir en off.",
        "Haz un pedido de prueba: debe completarse.",
        "Confirma que los cobros con error bajan del 5 %.",
      ],
      risk: "low",
      riskNote: "Se revierte en segundos y no requiere despliegue.",
      verification: "Los cobros con error bajan del 5 % y se mantienen así; un pedido de prueba se completa.",
      revisionNote: "Nueva propuesta: el cambio anterior no quedó aplicado.",
    },
  }),
  postmortem: (incident, alert, now) => {
    const { approved, resolvedAt, duration, actions, timeline } = narrative(incident, alert, now);
    return {
      summary: `Entre las ${t(alert.startedAt)} y las ${t(resolvedAt)} (${duration}), los clientes de la tienda no pudieron pagar sus pedidos: falló el 100 % de los cobros. La causa fue el flag «paymentUnreachable», que hizo que checkout enviara los cobros a una dirección inexistente. ${mitigationSentence(approved)} y el servicio se recuperó.`,
      impact: `${incident.impact} Duró ${duration}; los logs de checkout registran unos 1.300 cobros fallidos.`,
      cause: {
        statement:
          "El flag «paymentUnreachable» hizo que checkout llamara a badAddress:50051 en lugar del servicio de pagos. Se confirmó al desactivarlo: los errores desaparecieron.",
        certainty: "confirmed",
      },
      actions,
      verification: `Los cobros con error bajaron del 100 % a menos del 1 % segundos después del cambio y se mantuvieron bajo el umbral del 5 %. Lo confirmaste a las ${t(incident.verification?.confirmedAt ?? resolvedAt)}.`,
      timeline,
      pending: [
        "Restringir quién puede cambiar feature flags en la tienda.",
        "Alertar cuando se active un flag de falla.",
        "Hacer un pedido de prueba automático cada 5 minutos.",
      ],
      unknowns: ["Quién activó el flag: flagd no registra el autor del cambio."],
    };
  },
};

/* ----------------------------------------------------------- recommendations */

const recommendations: Scenario = {
  key: "recommendations",
  detectionDelayMs: 18 * 60 * SECOND,
  alert: () => ({
    title: "Recomendaciones lentas en la tienda",
    summary: "La latencia p95 de las recomendaciones subió a 1,8 s (umbral: 1 s).",
    service: "recommendation",
    severity: "sev3",
    signal: { label: "Latencia p95", unit: "s", threshold: 1, baseline: 0.12, peak: 1.8, max: 2.4 },
    rule: "Latencia p95 por encima de 1 s durante 5 minutos",
    source: "Tienda OTel · métricas de Prometheus",
    suggestedImpact: "Las páginas de producto cargan lento; las compras siguen funcionando.",
  }),
  investigation: (alert) => [
    {
      label: "Midiendo la latencia de las recomendaciones",
      source: "metrics",
      durationMs: 3600,
      finding: {
        source: "metrics",
        title: "La latencia p95 pasó de 0,12 s a 1,8 s",
        detail: `Empezó a subir a las ${t(alert.startedAt)} y no ha dejado de crecer.`,
        verdict: "supports",
        query: {
          tool: "Prometheus · webstore-metrics",
          window: "Última hora",
          text: 'histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="recommendation"}[5m])))',
        },
      },
    },
    {
      label: "Revisando el consumo de memoria",
      source: "metrics",
      durationMs: 4000,
      finding: {
        source: "metrics",
        title: "La memoria de recommendation creció de 180 MB a 1,4 GB",
        detail: "El crecimiento es constante, típico de una caché que nunca se vacía.",
        verdict: "supports",
        query: {
          tool: "Prometheus · webstore-metrics",
          window: "Última hora",
          text: 'process_runtime_cpython_memory_bytes{service_name="recommendation", type="rss"}',
        },
      },
    },
    {
      label: "Buscando errores en los logs",
      source: "logs",
      durationMs: 3800,
      finding: {
        source: "logs",
        title: "Sin errores en los logs de recommendation",
        detail: "Las respuestas llegan, solo que cada vez más lento.",
        verdict: "empty",
        query: {
          tool: "Elasticsearch · webstore-logs",
          window: "Última hora",
          text: 'resource.service.name:"recommendation" AND severity_text:"ERROR"',
        },
      },
    },
    {
      label: "Buscando cambios recientes: despliegues y feature flags",
      source: "changes",
      durationMs: 4000,
      finding: {
        source: "changes",
        title: "Se activó el flag «recommendationCacheFailure»",
        detail: `Cambió a on a las ${t(alert.startedAt - 30 * SECOND)}. No hubo despliegues.`,
        verdict: "supports",
        query: { tool: "flagd · demo.flagd.json", window: "Últimas 24 h", text: 'recommendationCacheFailure: "off" → "on"' },
      },
    },
    { label: "Formulando la hipótesis y la mitigación", source: "reasoning", durationMs: 2800 },
  ],
  hypothesis: () => ({
    statement:
      "El flag «recommendationCacheFailure» provoca una fuga de memoria en la caché de recomendaciones: la memoria crece sin límite y cada respuesta tarda más.",
    confidence: "medium",
    refutedIf: "Si la latencia no baja después de desactivar el flag y reiniciar el servicio.",
  }),
  proposal: () => ({
    summary: "Desactivar «recommendationCacheFailure» y reiniciar recommendation",
    steps: [
      "Cambia «recommendationCacheFailure» a off en /feature.",
      "Reinicia el servicio recommendation para liberar la memoria.",
      "Abre una página de producto: las recomendaciones deben cargar en menos de 1 s.",
    ],
    risk: "medium",
    riskNote: "Durante el reinicio (unos 20 s) la tienda no muestra recomendaciones; las compras no se afectan.",
    verification: "La latencia p95 vuelve a estar por debajo de 1 s.",
  }),
  revision: (_alert, comment) => ({
    steps: [
      { label: "Leyendo tu comentario", source: "reasoning", durationMs: 2400 },
      { label: "Buscando una opción sin reinicio", source: "reasoning", durationMs: 3200 },
    ],
    proposal: {
      summary: "Desactivar el flag sin reiniciar y esperar a que la caché se vacíe",
      steps: [
        "Cambia «recommendationCacheFailure» a off en /feature.",
        "Espera unos 10 minutos a que la caché expire.",
        "Abre una página de producto: las recomendaciones deben cargar en menos de 1 s.",
      ],
      risk: "low",
      riskNote: "Sin cortes, pero la latencia tarda unos 10 minutos en normalizarse.",
      verification: "La latencia p95 vuelve a estar por debajo de 1 s.",
      revisionNote: comment
        ? `Ajustada según tu comentario: «${comment}»`
        : "Alternativa después de que rechazaras la propuesta anterior.",
    },
  }),
  reinvestigation: () => ({
    steps: [
      {
        label: "Midiendo de nuevo la latencia",
        source: "metrics",
        durationMs: 3000,
        finding: {
          source: "metrics",
          title: "La latencia sigue alta",
          detail: "p95 en 1,7 s: el servicio no liberó la memoria.",
          verdict: "supports",
        },
      },
      { label: "Redactando una nueva propuesta", source: "reasoning", durationMs: 2400 },
    ],
    proposal: {
      summary: "Reiniciar recommendation otra vez con el flag apagado",
      steps: [
        "Comprueba en /feature que «recommendationCacheFailure» está en off.",
        "Reinicia el servicio recommendation.",
        "Abre una página de producto: las recomendaciones deben cargar en menos de 1 s.",
      ],
      risk: "medium",
      riskNote: "Unos 20 s sin recomendaciones.",
      verification: "La latencia p95 vuelve a estar por debajo de 1 s.",
      revisionNote: "Nueva propuesta: la memoria no se liberó con el primer intento.",
    },
  }),
  postmortem: (incident, alert, now) => {
    const { approved, resolvedAt, duration, actions, timeline } = narrative(incident, alert, now);
    return {
      summary: `Desde las ${t(alert.startedAt)} y durante ${duration}, las recomendaciones de la tienda fueron cada vez más lentas (p95 hasta 1,8 s). La causa fue una fuga de memoria activada por el flag «recommendationCacheFailure». ${mitigationSentence(approved)}.`,
      impact: `${incident.impact} No hubo errores ni compras perdidas.`,
      cause: {
        statement: "Fuga de memoria en la caché de recomendaciones activada por «recommendationCacheFailure».",
        certainty: "probable",
      },
      actions,
      verification: `La latencia p95 volvió a menos de 1 s. Lo confirmaste a las ${t(incident.verification?.confirmedAt ?? resolvedAt)}.`,
      timeline,
      pending: ["Limitar el tamaño de la caché de recomendaciones.", "Alertar por consumo de memoria, no solo por latencia."],
      unknowns: ["Si la fuga también ocurre con el flag apagado bajo tráfico alto."],
    };
  },
};

/* ------------------------------------------------------------------------ ads */

const ads: Scenario = {
  key: "ads",
  detectionDelayMs: 6 * 60 * SECOND,
  alert: () => ({
    title: "Errores intermitentes en anuncios",
    summary: "El 3,1 % de las solicitudes de anuncios falla (umbral: 2 %).",
    service: "ad",
    severity: "sev4",
    signal: { label: "Anuncios con error", unit: "%", threshold: 2, baseline: 0.2, peak: 3.1, max: 5 },
    rule: "Más del 2 % de las solicitudes de anuncios con error durante 5 minutos",
    source: "Tienda OTel · métricas de Prometheus",
    suggestedImpact: "Algunos anuncios no se muestran; no afecta las compras.",
  }),
  investigation: (alert) => [
    {
      label: "Midiendo la tasa de errores de anuncios",
      source: "metrics",
      durationMs: 3400,
      finding: {
        source: "metrics",
        title: "Falla 1 de cada 30 solicitudes de anuncios",
        detail: `3,1 % de error en AdService/GetAds desde las ${t(alert.startedAt)}.`,
        verdict: "supports",
        query: {
          tool: "Prometheus · webstore-metrics",
          window: "Últimos 30 min",
          text: 'sum(rate(traces_span_metrics_calls_total{service_name="ad", status_code="STATUS_CODE_ERROR"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))',
        },
      },
    },
    {
      label: "Buscando cambios recientes: despliegues y feature flags",
      source: "changes",
      durationMs: 3600,
      finding: {
        source: "changes",
        title: "Se activó el flag «adFailure»",
        detail: "El flag hace fallar una parte de las solicitudes de GetAds.",
        verdict: "supports",
        query: { tool: "flagd · demo.flagd.json", window: "Últimas 24 h", text: 'adFailure: "off" → "on"' },
      },
    },
    { label: "Formulando la hipótesis y la mitigación", source: "reasoning", durationMs: 2600 },
  ],
  hypothesis: () => ({
    statement: "El flag «adFailure» hace fallar una parte de las solicitudes de anuncios.",
    confidence: "high",
    refutedIf: "Si los errores siguen con el flag apagado.",
  }),
  proposal: () => ({
    summary: "Desactivar el flag «adFailure»",
    steps: ["Cambia «adFailure» a off en /feature.", "Recarga la tienda: los anuncios deben aparecer."],
    risk: "low",
    riskNote: "Se revierte en segundos.",
    verification: "Los anuncios con error bajan del 2 %.",
  }),
  revision: (_alert, comment) => ({
    steps: [{ label: "Leyendo tu comentario", source: "reasoning", durationMs: 2400 }],
    proposal: {
      summary: "Ocultar los anuncios mientras se revisa el flag",
      steps: ["Desactiva la sección de anuncios en la tienda.", "Revisa «adFailure» con calma."],
      risk: "low",
      riskNote: "La tienda se ve sin anuncios temporalmente.",
      verification: "No hay solicitudes de anuncios con error.",
      revisionNote: comment ? `Ajustada según tu comentario: «${comment}»` : "Alternativa a la propuesta rechazada.",
    },
  }),
  reinvestigation: () => ({
    steps: [{ label: "Midiendo de nuevo los errores", source: "metrics", durationMs: 3000 }],
    proposal: {
      summary: "Desactivar «adFailure» y comprobar que quedó guardado",
      steps: ["Cambia «adFailure» a off en /feature y pulsa «Save».", "Recarga /feature: debe seguir en off."],
      risk: "low",
      riskNote: "Se revierte en segundos.",
      verification: "Los anuncios con error bajan del 2 %.",
      revisionNote: "Nueva propuesta: el cambio anterior no quedó aplicado.",
    },
  }),
  postmortem: (incident, alert, now) => {
    const { approved, duration, actions, timeline } = narrative(incident, alert, now);
    return {
      summary: `Durante ${duration} falló el 3 % de las solicitudes de anuncios por el flag «adFailure». ${mitigationSentence(approved)}.`,
      impact: incident.impact,
      cause: { statement: "El flag «adFailure» estaba activo.", certainty: "confirmed" },
      actions,
      verification: "Los anuncios con error volvieron a menos del 0,5 %.",
      timeline,
      pending: ["Alertar cuando se active un flag de falla."],
      unknowns: [],
    };
  },
};

/* ------------------------------------------------- history (closed incidents) */

const cart: Scenario = {
  key: "cart",
  detectionDelayMs: 70 * SECOND,
  alert: () => ({
    title: "El carrito no guarda productos",
    summary: "El 48 % de las solicitudes al carrito falla (umbral: 5 %).",
    service: "cart",
    severity: "sev2",
    signal: { label: "Solicitudes al carrito con error", unit: "%", threshold: 5, baseline: 0.2, peak: 48, max: 100 },
    rule: "Más del 5 % de las solicitudes al carrito con error durante 2 minutos",
    source: "Tienda OTel · métricas de Prometheus",
    suggestedImpact: "Los clientes no pueden agregar productos al carrito.",
  }),
  investigation: () => [
    {
      label: "Midiendo la tasa de errores del carrito",
      source: "metrics",
      durationMs: 3000,
      finding: {
        source: "metrics",
        title: "Falla casi la mitad de las solicitudes al carrito",
        detail: "48 % de error en CartService/AddItem y EmptyCart.",
        verdict: "supports",
      },
    },
    {
      label: "Buscando cambios recientes: despliegues y feature flags",
      source: "changes",
      durationMs: 3000,
      finding: {
        source: "changes",
        title: "Se activó el flag «cartFailure»",
        detail: "El flag hace que cart use una conexión inválida a Valkey.",
        verdict: "supports",
      },
    },
  ],
  hypothesis: () => ({
    statement: "El flag «cartFailure» hace que el carrito use una conexión inválida a Valkey y falle al guardar.",
    confidence: "high",
    refutedIf: "Si los errores siguen con el flag apagado.",
  }),
  proposal: () => ({
    summary: "Desactivar el flag «cartFailure»",
    steps: ["Cambia «cartFailure» a off en /feature.", "Agrega un producto al carrito: debe guardarse."],
    risk: "low",
    riskNote: "Se revierte en segundos.",
    verification: "Las solicitudes al carrito con error bajan del 5 %.",
  }),
  revision: (alert, comment) => ({ steps: [], proposal: { ...cart.proposal(alert), revisionNote: comment } }),
  reinvestigation: (alert) => ({ steps: [], proposal: cart.proposal(alert) }),
  postmortem: (incident, alert, now) => {
    const { duration, actions, timeline } = narrative(incident, alert, now);
    return {
      summary: `Durante ${duration} los clientes no pudieron agregar productos al carrito. El flag «cartFailure» rompía la conexión del carrito con Valkey; al desactivarlo el servicio se recuperó.`,
      impact: `${incident.impact} Alrededor de 40 carritos abandonados.`,
      cause: { statement: "El flag «cartFailure» configuraba una conexión inválida a Valkey.", certainty: "confirmed" },
      actions,
      verification: "Las solicitudes con error volvieron a 0,2 % y un carrito de prueba se guardó.",
      timeline,
      pending: ["Agregar un chequeo de salud de Valkey al carrito."],
      unknowns: [],
    };
  },
};

const images: Scenario = {
  key: "images",
  detectionDelayMs: 4 * 60 * SECOND,
  alert: () => ({
    title: "Imágenes de productos lentas",
    summary: "Las imágenes tardan 5,2 s en cargar (umbral: 2 s).",
    service: "image-provider",
    severity: "sev3",
    signal: { label: "Carga de imágenes (p95)", unit: "s", threshold: 2, baseline: 0.2, peak: 5.2, max: 6 },
    rule: "Carga de imágenes p95 por encima de 2 s durante 5 minutos",
    source: "Tienda OTel · métricas de Prometheus",
    suggestedImpact: "El catálogo se ve sin imágenes durante varios segundos.",
  }),
  investigation: () => [
    {
      label: "Midiendo el tiempo de carga de imágenes",
      source: "metrics",
      durationMs: 3000,
      finding: {
        source: "metrics",
        title: "Cada imagen tarda unos 5 s",
        detail: "La demora es constante, no depende del tamaño.",
        verdict: "supports",
      },
    },
    {
      label: "Buscando cambios recientes: despliegues y feature flags",
      source: "changes",
      durationMs: 3000,
      finding: {
        source: "changes",
        title: "Se activó el flag «imageSlowLoad»",
        detail: "Inyecta una demora fija en el proxy de imágenes.",
        verdict: "supports",
      },
    },
  ],
  hypothesis: () => ({
    statement: "El flag «imageSlowLoad» inyecta una demora de 5 s en el proxy de imágenes.",
    confidence: "high",
    refutedIf: "Si la demora sigue con el flag apagado.",
  }),
  proposal: () => ({
    summary: "Desactivar el flag «imageSlowLoad»",
    steps: ["Cambia «imageSlowLoad» a off en /feature.", "Recarga el catálogo: las imágenes deben cargar al instante."],
    risk: "low",
    riskNote: "Se revierte en segundos.",
    verification: "La carga de imágenes p95 baja de 2 s.",
  }),
  revision: (alert, comment) => ({ steps: [], proposal: { ...images.proposal(alert), revisionNote: comment } }),
  reinvestigation: (alert) => ({ steps: [], proposal: images.proposal(alert) }),
  postmortem: (incident, alert, now) => {
    const { duration, actions, timeline } = narrative(incident, alert, now);
    return {
      summary: `Durante ${duration} las imágenes del catálogo tardaron unos 5 s en cargar por el flag «imageSlowLoad». Al desactivarlo la carga volvió a la normalidad.`,
      impact: incident.impact,
      cause: { statement: "El flag «imageSlowLoad» inyectaba una demora fija.", certainty: "confirmed" },
      actions,
      verification: "La carga p95 volvió a 0,2 s.",
      timeline,
      pending: [],
      unknowns: [],
    };
  },
};

export const SCENARIOS: Record<ScenarioKey, Scenario> = { payments, recommendations, ads, cart, images };

export const LIVE_SCENARIOS: { key: ScenarioKey; label: string }[] = [
  { key: "payments", label: "Pagos fallando (SEV1)" },
  { key: "recommendations", label: "Recomendaciones lentas (SEV3)" },
  { key: "ads", label: "Errores en anuncios (SEV4)" },
];
