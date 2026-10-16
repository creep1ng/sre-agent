import { createAdministrativeApiClient, createMemoryCredentialStore } from "../api/client.js";

// One session for every console view, shaped like connectSharedSession (ADR-009) so the
// SharedWorker of #486 can replace it here. Until then the key lives in this tab's memory:
// a reload asks for it again, and no page script can read it back.
export function createTabSession() {
  const credentialStore = createMemoryCredentialStore();
  const api = createAdministrativeApiClient({ credentialStore });
  const listeners = new Set();
  let generation = 0;
  let state = Object.freeze({ token: "tab:0", phase: "anonymous", principalId: null, reason: null });

  function emit(next) {
    state = Object.freeze(next);
    listeners.forEach((listener) => listener(state));
  }

  function nextToken() {
    generation += 1;
    return `tab:${generation}`;
  }

  // Each accepted change starts a generation; a later change always wins (ADR-009, section 4).
  function invalidate(reason) {
    credentialStore.clear();
    emit({ token: nextToken(), phase: "anonymous", principalId: null, reason });
  }

  async function validate(token) {
    try {
      const identity = await api.getWhoAmI();
      if (state.token !== token) return;
      if (typeof identity?.principal_id !== "string" || identity.principal_id === "") {
        emit({ token, phase: "validating", principalId: null, reason: "invalid_response" });
        return;
      }
      emit({ token, phase: "active", principalId: identity.principal_id, reason: null });
    } catch (error) {
      if (state.token !== token) return;
      if (error?.kind === "authentication") invalidate("invalid_credential");
      else emit({ token, phase: "validating", principalId: null, reason: error?.kind ?? "api" });
    }
  }

  // A 401 under the current generation ends the session for every view; one that belongs to an
  // earlier generation is ignored. A 403 only concerns the operation that received it.
  const client = Object.freeze(
    Object.fromEntries(
      Object.entries(api)
        .filter(([, value]) => typeof value === "function")
        .map(([name, method]) => [
          name,
          async (...args) => {
            const token = state.token;
            try {
              return await method(...args);
            } catch (error) {
              if (error?.kind === "authentication" && state.token === token && state.phase === "active") {
                invalidate("credential_rejected");
              }
              throw error;
            }
          },
        ]),
    ),
  );

  return Object.freeze({
    client,
    get state() {
      return state;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setCredential(value) {
      if (typeof value !== "string" || !/^[\x21-\x7e]+$/.test(value)) {
        throw new TypeError("A non-empty printable bearer credential is required.");
      }
      const token = nextToken();
      credentialStore.set(value);
      emit({ token, phase: "validating", principalId: null, reason: null });
      validate(token);
    },
    logout() {
      invalidate("logout");
    },
    retry() {
      if (state.phase === "validating") validate(state.token);
    },
  });
}
