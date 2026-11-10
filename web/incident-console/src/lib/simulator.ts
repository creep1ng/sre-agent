import { appMode } from "./mode";

type Simulator = typeof import("@/simulator");

/**
 * The scenario simulator (`src/simulator/`), loaded before the first render in mock mode and
 * `null` otherwise. Only a build with `CONSOLE_SIMULATOR=1` holds it: without the variable the
 * import below is dead code and the bundle has no simulator chunk.
 */
export let simulator: Simulator | null = null;

export async function loadSimulator(): Promise<void> {
  if (__CONSOLE_SIMULATOR__ && appMode === "mock") simulator = await import("@/simulator");
}
