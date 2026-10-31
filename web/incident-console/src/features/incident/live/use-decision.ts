import { useCallback, useEffect, useRef, useState } from "react";
import { incidentApi } from "@/lib/incident-api";
import { useLive } from "@/lib/live";
import type { LiveIncident } from "@/lib/live-incident";

export type Choice = "approve" | "reject";
export type DecisionError = "forbidden" | "stale" | "failed";

// randomUUID needs a secure context; a console served over plain http on a LAN has none.
const nonce = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");

const COMMAND: Record<Choice, string> = { approve: "approve_mitigation", reject: "reject_mitigation" };

/**
 * Who you are (to tell your decisions from other people's) and the governed decision on the
 * proposed mitigation, the same command the previous console sends: bound to the incident
 * version on screen, with one idempotency key per submission that a manual retry reuses.
 */
export function useDecision(live: LiveIncident & { refresh: () => void }) {
  const token = useLive((s) => s.token);
  const [me, setMe] = useState<string | null | undefined>(undefined);
  const [sending, setSending] = useState<Choice | null>(null);
  const [error, setError] = useState<DecisionError | null>(null);
  const submission = useRef<{ choice: Choice; version: number; key: string } | null>(null);

  useEffect(() => {
    setMe(undefined);
    if (!token) return;
    const abort = new AbortController();
    void incidentApi.whoami(token, abort.signal).then(
      (result) => setMe(result.kind === "ok" ? result.body.principal_id : null),
      () => undefined,
    );
    return () => abort.abort();
  }, [token]);

  const decide = useCallback(
    async (choice: Choice, run: string) => {
      const detail = live.detail;
      if (!token || !detail || !me || sending) return;
      const same = submission.current?.choice === choice && submission.current.version === detail.version;
      if (!same) submission.current = { choice, version: detail.version, key: `console-${COMMAND[choice]}-${nonce()}` };
      const { key } = submission.current!;
      setSending(choice);
      setError(null);
      const body = {
        command: COMMAND[choice],
        expected_incident_version: detail.version,
        actor: "human",
        actor_reference: { reference_version: "1.0.0", principal_id: me },
        turn_id: null,
        disposition: null,
        comment: null,
        authorization: { action: "run.approve", resource: { type: "incident_workflow", id: "incident-response" } },
      };
      let result;
      try {
        result = await incidentApi.command(token, detail.incident_id, run, body, key, new AbortController().signal);
      } catch {
        result = { kind: "transient" as const };
      }
      // A failed send keeps its key, so trying again replays it instead of deciding twice.
      if (result.kind === "ok" || result.kind === "conflict") submission.current = null;
      setError(result.kind === "ok" ? null : result.kind === "forbidden" ? "forbidden" : result.kind === "conflict" ? "stale" : "failed");
      setSending(null);
      live.refresh();
    },
    [live, token, me, sending],
  );

  return { me, sending, error, decide };
}
