import type { Certainty, Confidence, EvidenceSource, Severity, TriageStatus, Verdict } from "./types";

export type Tone = "info" | "warning" | "success" | "critical" | "neutral" | "brand";

export const TONE_CLASSES: Record<Tone, string> = {
  info: "bg-info-soft text-info border-info-line",
  warning: "bg-warning-soft text-warning border-warning-line",
  success: "bg-success-soft text-success border-success-line",
  critical: "bg-critical-soft text-critical border-critical-line",
  neutral: "bg-muted text-muted-foreground border-border",
  brand: "bg-secondary text-secondary-foreground border-brand-soft",
};

export const TONE_DOT: Record<Tone, string> = {
  info: "bg-info",
  warning: "bg-warning",
  success: "bg-success",
  critical: "bg-critical",
  neutral: "bg-muted-foreground",
  brand: "bg-primary",
};

export const TONE_TEXT: Record<Tone, string> = {
  info: "text-info",
  warning: "text-warning",
  success: "text-success",
  critical: "text-critical",
  neutral: "text-muted-foreground",
  brand: "text-primary",
};

export const SEVERITY: Record<
  Severity,
  { short: string; label: string; description: string; tone: Tone; rank: number }
> = {
  sev1: {
    short: "SEV1",
    label: "Crítica",
    description: "Los clientes no pueden usar una función clave, como pagar.",
    tone: "critical",
    rank: 1,
  },
  sev2: {
    short: "SEV2",
    label: "Alta",
    description: "Una función importante falla para muchos clientes.",
    tone: "warning",
    rank: 2,
  },
  sev3: {
    short: "SEV3",
    label: "Media",
    description: "Algo funciona mal o lento, pero hay alternativa.",
    tone: "brand",
    rank: 3,
  },
  sev4: {
    short: "SEV4",
    label: "Baja",
    description: "Una molestia menor que no afecta lo esencial.",
    tone: "neutral",
    rank: 4,
  },
};

export const SEVERITIES: Severity[] = ["sev1", "sev2", "sev3", "sev4"];

export const TRIAGE: Record<TriageStatus, { label: string; tone: Tone }> = {
  new: { label: "Nueva", tone: "brand" },
  triaging: { label: "En triage", tone: "warning" },
  declared: { label: "Declarada", tone: "info" },
  linked: { label: "Vinculada", tone: "info" },
  dismissed: { label: "Descartada", tone: "neutral" },
};

export const SOURCE_LABEL: Record<EvidenceSource, string> = {
  metrics: "Métricas",
  logs: "Logs",
  traces: "Trazas",
  changes: "Cambios recientes",
  knowledge: "Base de conocimiento",
  reasoning: "Razonamiento",
};

export const VERDICT: Record<Verdict, { label: string; tone: Tone }> = {
  supports: { label: "Respalda la hipótesis", tone: "success" },
  empty: { label: "No encontró nada", tone: "neutral" },
  contradicts: { label: "Contradice la hipótesis", tone: "critical" },
  context: { label: "Contexto útil", tone: "info" },
};

/** While the agent is still investigating there is no hypothesis to back yet. */
export const LIVE_VERDICT: Record<Verdict, { label: string; tone: Tone }> = {
  supports: { label: "Relevante", tone: "success" },
  empty: { label: "No encontró nada", tone: "neutral" },
  contradicts: { label: "Descarta una causa", tone: "critical" },
  context: { label: "Contexto útil", tone: "info" },
};

export const CONFIDENCE: Record<Confidence, { label: string; level: number }> = {
  low: { label: "Confianza baja", level: 1 },
  medium: { label: "Confianza media", level: 2 },
  high: { label: "Confianza alta", level: 3 },
};

export const RISK: Record<"low" | "medium" | "high", { label: string; tone: Tone }> = {
  low: { label: "Riesgo bajo", tone: "success" },
  medium: { label: "Riesgo medio", tone: "warning" },
  high: { label: "Riesgo alto", tone: "critical" },
};

export const CERTAINTY: Record<Certainty, { label: string; hint: string }> = {
  confirmed: { label: "Confirmada", hint: "La mitigación que la atacaba resolvió el problema." },
  probable: { label: "Probable", hint: "La evidencia apunta a ella, pero no se comprobó del todo." },
  hypothesis: { label: "Hipótesis", hint: "Es la mejor explicación disponible, sin comprobar." },
  unknown: { label: "Desconocida", hint: "Todavía no se sabe por qué pasó." },
};

export const DISMISS_REASONS = [
  "Falsa alarma",
  "Se resolvió sola",
  "Mantenimiento planificado",
  "Ya lo estoy atendiendo en otro lado",
];
