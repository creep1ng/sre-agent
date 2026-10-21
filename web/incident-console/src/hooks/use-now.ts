import { create } from "zustand";

/** One shared clock for relative times and running timers. */
export const useClock = create<{ now: number }>(() => ({ now: Date.now() }));

export function useNow(): number {
  return useClock((state) => state.now);
}

export function setClock(now: number) {
  useClock.setState({ now });
}
