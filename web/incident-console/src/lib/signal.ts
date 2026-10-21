import type { Alert } from "./types";

export interface SignalPoint {
  t: number;
  v: number;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Deterministic noise in [0, 1) for a seed and a time bucket, so charts never jitter. */
function noise(seed: string, bucket: number): number {
  let x = hash(`${seed}:${bucket}`);
  x ^= x << 13;
  x ^= x >>> 17;
  x ^= x << 5;
  return ((x >>> 0) % 10_000) / 10_000;
}

const RAMP_UP_MS = 45_000;
const RAMP_DOWN_MS = 9_000;

function smooth(progress: number): number {
  const p = Math.min(1, Math.max(0, progress));
  return p * p * (3 - 2 * p);
}

export function signalValue(alert: Alert, t: number, bucket: number): number {
  const { baseline, peak, max } = alert.signal;
  const calm = baseline * (0.55 + 0.9 * noise(alert.id, bucket));
  if (t < alert.startedAt) return calm;

  const failing = Math.min(max, peak * (0.985 + 0.03 * noise(`${alert.id}:p`, bucket)));
  let value = calm + (failing - calm) * smooth((t - alert.startedAt) / RAMP_UP_MS);

  if (alert.recoveryStartAt !== undefined && t >= alert.recoveryStartAt) {
    const progress = smooth((t - alert.recoveryStartAt) / RAMP_DOWN_MS);
    value = value + (calm - value) * progress;
  }
  return Math.min(max, Math.max(0, value));
}

export function buildSeries(
  alert: Alert,
  now: number,
  windowMs: number,
  stepMs: number,
): SignalPoint[] {
  const end = Math.floor(now / stepMs) * stepMs;
  const points: SignalPoint[] = [];
  for (let t = end - windowMs; t <= end; t += stepMs) {
    points.push({ t, v: signalValue(alert, t, Math.floor(t / stepMs)) });
  }
  points.push({ t: now, v: signalValue(alert, now, Math.floor(now / stepMs)) });
  return points;
}

export function currentValue(alert: Alert, now: number): number {
  return signalValue(alert, now, Math.floor(now / 10_000));
}

export function isAboveThreshold(alert: Alert, now: number): boolean {
  return currentValue(alert, now) > alert.signal.threshold;
}
