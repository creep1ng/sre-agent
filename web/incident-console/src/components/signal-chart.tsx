import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useNow } from "@/hooks/use-now";
import { formatSignal, formatTime } from "@/lib/format";
import { buildSeries, type SignalPoint } from "@/lib/signal";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

function linePath(points: SignalPoint[], x: (t: number) => number, y: (v: number) => number) {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
}

function niceTicks(max: number, unit: "%" | "s"): number[] {
  if (unit === "%") {
    if (max >= 50) return [0, 25, 50, 75, 100].filter((v) => v <= max);
    const step = max <= 5 ? 1 : max <= 10 ? 2 : 5;
    return Array.from({ length: Math.floor(max / step) + 1 }, (_, i) => i * step);
  }
  const step = max <= 1 ? 0.25 : max <= 3 ? 0.5 : 1;
  return Array.from({ length: Math.floor(max / step) + 1 }, (_, i) => Math.round(i * step * 100) / 100);
}

/** Inline trend for alert cards: the series, its threshold and the current value. */
export function Sparkline({ alert, className }: { alert: Alert; className?: string }) {
  const now = useNow();
  const points = useMemo(() => buildSeries(alert, now, 30 * 60_000, 30_000), [alert, now]);
  const width = 132;
  const height = 40;
  const pad = 5;
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t;
  const x = (t: number) => pad + ((t - t0) / (t1 - t0)) * (width - pad * 2);
  const y = (v: number) => height - pad - (v / alert.signal.max) * (height - pad * 2);
  const last = points[points.length - 1];
  const gradient = useId();
  const path = linePath(points, x, y);
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("overflow-visible", className)}
      role="img"
      aria-label={`${alert.signal.label}: ${formatSignal(last.v, alert.signal.unit)} ahora; umbral ${formatSignal(alert.signal.threshold, alert.signal.unit)}`}
    >
      <defs>
        <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--chart-fill)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--chart-fill)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line
        x1={pad}
        x2={width - pad}
        y1={y(alert.signal.threshold)}
        y2={y(alert.signal.threshold)}
        stroke="var(--chart-threshold)"
        strokeWidth={1}
        strokeDasharray="3 3"
        opacity={0.8}
      />
      <path d={`${path}L${x(t1)},${height - pad}L${x(t0)},${height - pad}Z`} fill={`url(#${gradient})`} />
      <path d={path} fill="none" stroke="var(--chart-line)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(last.t)} cy={y(last.v)} r={4} fill="var(--chart-line)" stroke="var(--card)" strokeWidth={2} />
    </svg>
  );
}

interface SignalChartProps {
  alert: Alert;
  windowMs?: number;
  stepMs?: number;
  height?: number;
  className?: string;
}

/** Verification chart: last minutes of the signal against its threshold, with a hover readout. */
export function SignalChart({ alert, windowMs = 10 * 60_000, stepMs = 10_000, height = 200, className }: SignalChartProps) {
  const now = useNow();
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const points = useMemo(() => buildSeries(alert, now, windowMs, stepMs), [alert, now, windowMs, stepMs]);
  const gradient = useId();
  const { unit, threshold, max, label } = alert.signal;

  const margin = { top: 14, right: 64, bottom: 26, left: 44 };
  const innerWidth = Math.max(0, width - margin.left - margin.right);
  const innerHeight = height - margin.top - margin.bottom;
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t;
  const x = (t: number) => margin.left + ((t - t0) / (t1 - t0)) * innerWidth;
  const y = (v: number) => margin.top + innerHeight - (v / max) * innerHeight;
  const ticks = niceTicks(max, unit);
  const last = points[points.length - 1];
  const path = linePath(points, x, y);
  const xTicks = [t0, t0 + (t1 - t0) / 2, t1];
  const active = hover !== null ? points[hover] : null;

  function nearest(clientX: number, element: SVGSVGElement) {
    const rect = element.getBoundingClientRect();
    const px = clientX - rect.left;
    const t = t0 + ((px - margin.left) / innerWidth) * (t1 - t0);
    let best = 0;
    for (let i = 1; i < points.length; i += 1) {
      if (Math.abs(points[i].t - t) < Math.abs(points[best].t - t)) best = i;
    }
    return best;
  }

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    setHover(nearest(event.clientX, event.currentTarget));
  }

  function onKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const start = hover ?? points.length - 1;
    const next = event.key === "ArrowLeft" ? Math.max(0, start - 1) : Math.min(points.length - 1, start + 1);
    setHover(next);
  }

  return (
    <div ref={ref} className={cn("relative w-full", className)}>
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          tabIndex={0}
          aria-label={`${label} en los últimos ${Math.round(windowMs / 60_000)} minutos. Ahora: ${formatSignal(last.v, unit)}. Umbral: ${formatSignal(threshold, unit)}.`}
          className="touch-none rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
          onBlur={() => setHover(null)}
          onKeyDown={onKeyDown}
        >
          <defs>
            <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-fill)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--chart-fill)" stopOpacity="0.02" />
            </linearGradient>
          </defs>

          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={margin.left}
                x2={margin.left + innerWidth}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--chart-grid)"
                strokeWidth={1}
              />
              <text
                x={margin.left - 8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                className="fill-muted-foreground text-[11px] tabular"
              >
                {formatSignal(tick, unit)}
              </text>
            </g>
          ))}

          <line
            x1={margin.left}
            x2={margin.left + innerWidth}
            y1={y(threshold)}
            y2={y(threshold)}
            stroke="var(--chart-threshold)"
            strokeWidth={1.5}
            strokeDasharray="5 4"
          />
          <text
            x={margin.left + 6}
            y={y(threshold) - 6}
            className="fill-muted-foreground text-[11px] font-medium"
          >
            Umbral {formatSignal(threshold, unit)}
          </text>

          <path d={`${path}L${x(t1)},${y(0)}L${x(t0)},${y(0)}Z`} fill={`url(#${gradient})`} />
          <path d={path} fill="none" stroke="var(--chart-line)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

          <circle cx={x(last.t)} cy={y(last.v)} r={4.5} fill="var(--chart-line)" stroke="var(--card)" strokeWidth={2} />
          <text x={x(last.t) + 10} y={y(last.v)} dy="0.32em" className="fill-foreground text-xs font-semibold">
            {formatSignal(last.v, unit)}
          </text>

          {xTicks.map((tick, index) => (
            <text
              key={tick}
              x={x(tick)}
              y={height - 6}
              textAnchor={index === 0 ? "start" : index === 2 ? "end" : "middle"}
              className="fill-muted-foreground text-[11px] tabular"
            >
              {index === 2 ? "ahora" : formatTime(tick)}
            </text>
          ))}

          {active && (
            <g pointerEvents="none">
              <line
                x1={x(active.t)}
                x2={x(active.t)}
                y1={margin.top}
                y2={margin.top + innerHeight}
                stroke="var(--muted-foreground)"
                strokeWidth={1}
                opacity={0.5}
              />
              <circle cx={x(active.t)} cy={y(active.v)} r={4.5} fill="var(--chart-line)" stroke="var(--card)" strokeWidth={2} />
            </g>
          )}
        </svg>
      )}
      {active && (
        <div
          className="pointer-events-none absolute top-1 z-10 -translate-x-1/2 rounded-lg border bg-popover px-2.5 py-1.5 text-xs shadow-md"
          style={{ left: Math.min(Math.max(x(active.t), 60), width - 60) }}
        >
          <div className="font-semibold text-foreground">{formatSignal(active.v, unit)}</div>
          <div className="text-muted-foreground">{formatTime(active.t)}</div>
        </div>
      )}
    </div>
  );
}

/** Table twin of the chart, for reading the values without hovering. */
export function SignalTable({ alert, count = 8 }: { alert: Alert; count?: number }) {
  const now = useNow();
  const points = useMemo(() => buildSeries(alert, now, 10 * 60_000, 60_000).slice(-count), [alert, now, count]);
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left text-muted-foreground">
          <th className="py-1 font-medium">Hora</th>
          <th className="py-1 text-right font-medium">{alert.signal.label}</th>
        </tr>
      </thead>
      <tbody className="tabular">
        {points.map((point) => (
          <tr key={point.t} className="border-t border-border/60">
            <td className="py-1">{formatTime(point.t)}</td>
            <td className="py-1 text-right">{formatSignal(point.v, alert.signal.unit)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
