import { ApiClientError } from "/public/api/client.js";

// The reasoning the incident recorded from its investigation (hypotheses, the evidence they cite
// and the proposed mitigation). It arrives only with run.read_context, in the `reasoning` block
// of GET .../runs/{run_id}/context; the war room and Decisiones read it here. A refusal is an
// honest state of the view, never a page failure. Text comes from the model, in English, and is
// always set as text, never as markup.
export const CONFIDENCE = Object.freeze({
  low: Object.freeze({ label: "Confianza baja", tone: "warning" }),
  medium: Object.freeze({ label: "Confianza media", tone: "info" }),
  high: Object.freeze({ label: "Confianza alta", tone: "success" }),
});

export const HYPOTHESIS_STATUS = Object.freeze({
  open: "abierta",
  supported: "respaldada",
  refuted: "refutada",
  superseded: "reemplazada",
});

const MAX_SERIES = 6;

// { kind: "ok", reasoning } | { kind: "forbidden" } | { kind: "unavailable" }.
export async function readReasoning(client, incidentId, runId) {
  try {
    const context = await client.getRunContext(incidentId, runId);
    const reasoning = context?.reasoning;
    if (
      !reasoning ||
      typeof reasoning !== "object" ||
      !Array.isArray(reasoning.hypotheses) ||
      !Array.isArray(reasoning.evidence)
    ) {
      return { kind: "unavailable" };
    }
    return { kind: "ok", reasoning };
  } catch (error) {
    if (error instanceof ApiClientError && error.kind === "authorization") {
      return { kind: "forbidden" };
    }
    return { kind: "unavailable" };
  }
}

export function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

export function badge(entry, fallback) {
  const node = element("span", "ma-badge", entry?.label ?? String(fallback ?? "—"));
  if (entry?.tone) node.dataset.tone = entry.tone;
  return node;
}

function clip(text, limit) {
  const flat = String(text).replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat;
}

function sampleValue(entry) {
  const pair = Array.isArray(entry?.value) ? entry.value : entry?.values?.at?.(-1);
  const value = Array.isArray(pair) ? Number(pair[1]) : Number.NaN;
  return Number.isFinite(value) ? String(Math.round(value * 100) / 100) : "—";
}

// A short reading of the bounded result summary: series and their last value for Prometheus,
// the hit count and the first message for logs, otherwise the first characters of the text.
export function resultSummary(summary) {
  if (typeof summary !== "string" || summary.trim() === "") return "—";
  let parsed = null;
  try {
    parsed = JSON.parse(summary);
  } catch {
    parsed = null;
  }
  if (parsed && Array.isArray(parsed.result)) {
    if (parsed.result.length === 0) return "Sin series en la ventana consultada.";
    const series = parsed.result.slice(0, MAX_SERIES).map((entry) => {
      const labels = Object.values(entry?.metric ?? {}).join(", ") || "serie";
      return `${labels}: ${sampleValue(entry)}`;
    });
    const rest = parsed.result.length - MAX_SERIES;
    return series.join(" · ") + (rest > 0 ? ` · +${rest} series` : "");
  }
  if (parsed && Array.isArray(parsed.documents)) {
    const total = Number.isInteger(parsed.total) ? parsed.total : parsed.documents.length;
    const first = parsed.documents.find((doc) => typeof doc?._source?.body === "string");
    const message = first ? ` · primero: ${clip(first._source.body, 120)}` : "";
    return `${total} ${total === 1 ? "documento" : "documentos"}${message}`;
  }
  // The stored summary is bounded, so a long log result arrives cut and is no longer JSON.
  const total = summary.match(/^\{"total":(\d+)/);
  if (total) {
    const body = summary.match(/"body":"((?:[^"\\]|\\.)*)"/);
    let message = "";
    try {
      message = body ? ` · primero: ${clip(JSON.parse(`"${body[1]}"`), 120)}` : "";
    } catch {
      message = "";
    }
    return `${total[1]} documentos${message} (resumen acotado)`;
  }
  return clip(summary, 240);
}

function english(tag, className, content) {
  const node = element(tag, className, content);
  node.lang = "en";
  return node;
}

// The most recent hypothesis is the current one; earlier ones stay counted.
export function hypothesisBlock(hypotheses) {
  const current = hypotheses[hypotheses.length - 1];
  const block = element("div", "reasoning__hypothesis");
  block.append(english("p", "reasoning__statement", current.statement ?? "—"));
  const meta = element("p", "reasoning__meta");
  const status = HYPOTHESIS_STATUS[current.status] ?? current.status;
  meta.append(badge(CONFIDENCE[current.confidence], current.confidence));
  if (status) meta.append(` Hipótesis ${status}`);
  const cited = Array.isArray(current.supporting_evidence) ? current.supporting_evidence.length : 0;
  meta.append(` · cita ${cited} ${cited === 1 ? "evidencia" : "evidencias"}`);
  if (hypotheses.length > 1) meta.append(` · ${hypotheses.length} hipótesis registradas`);
  block.append(meta);
  return { block, current };
}

export function evidenceItem(item, citedIds) {
  const entry = element("li", "reasoning__evidence");
  const head = element("p", "reasoning__evidence-head");
  head.append(element("span", "ma-badge ma-badge--plain", item.tool ?? item.source ?? "evidencia"));
  if (item.datasource_uid) head.append(" ", element("span", "ma-mono", item.datasource_uid));
  if (item.time_window) head.append(` · ventana ${item.time_window}`);
  if (item.source) head.append(` · fuente ${item.source}`);
  if (citedIds.has(item.evidence_id)) {
    const cited = element("span", "ma-badge", "Citada por la hipótesis");
    cited.dataset.tone = "info";
    head.append(" ", cited);
  }
  entry.append(head);
  if (item.query) entry.append(element("code", "reasoning__query", item.query));
  entry.append(element("p", "reasoning__result", resultSummary(item.summary)));
  const request = element("p", "reasoning__request ma-muted");
  // Tool evidence names the governed MCP request; knowledge-base evidence names the model reply.
  request.append(
    item.tool && item.tool !== "bok.search" ? "Solicitud MCP: " : "Solicitud gobernada: ",
    element("span", "ma-mono", typeof item.request_id === "string" ? item.request_id : "sin registrar"),
  );
  entry.append(request);
  return entry;
}
