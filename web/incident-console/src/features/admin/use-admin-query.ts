import { useCallback, useEffect, useRef, useState } from "react";
import { idempotencyKey, type AdminError, type AdminResult } from "@/lib/admin-api";
import { useLive } from "@/lib/live";

export type QueryState<T> =
  | { phase: "idle" }
  | { phase: "loading"; previous?: T }
  | { phase: "ok"; data: T }
  | { phase: "error"; error: AdminError };

/**
 * Reads `load` while the session has a credential and whenever `key` changes. A late answer
 * from an older key or an older session never overwrites a newer one.
 */
export function useAdminQuery<T>(load: (() => Promise<AdminResult<T>>) | null, key: string) {
  const token = useLive((state) => state.token);
  const [state, setState] = useState<QueryState<T>>({ phase: "idle" });
  const generation = useRef(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  const run = useCallback(() => {
    const current = ++generation.current;
    const fn = loadRef.current;
    if (!token || !fn) {
      setState({ phase: "idle" });
      return;
    }
    setState((previous) => ({ phase: "loading", previous: previous.phase === "ok" ? previous.data : undefined }));
    void fn().then((result) => {
      if (current !== generation.current) return;
      setState(result.ok ? { phase: "ok", data: result.body } : { phase: "error", error: result.error });
    });
  }, [token]);

  useEffect(run, [run, key, load === null]);

  const data = state.phase === "ok" ? state.data : state.phase === "loading" ? state.previous : undefined;
  return { state, data, reload: run };
}

/** Reuses the idempotency key while the same body is retried; a new body gets a new key. */
export function useRetryKey(prefix: string) {
  const pending = useRef<{ body: string; key: string } | null>(null);
  return {
    keyFor(body: unknown) {
      const text = JSON.stringify(body);
      if (pending.current?.body !== text) pending.current = { body: text, key: idempotencyKey(prefix) };
      return pending.current.key;
    },
    settle() {
      pending.current = null;
    },
  };
}
