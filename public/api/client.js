const STATUS_KINDS = Object.freeze({
  401: "authentication",
  403: "authorization",
  404: "not_found",
  409: "conflict",
});
const credentialValues = new WeakMap();
const sessionSenders = new WeakMap();
const SESSION_PROTOCOL = 1;

export class ApiClientError extends Error {
  constructor(kind, message, options = {}) {
    super(message, options.cause ? { cause: options.cause } : undefined);
    this.name = "ApiClientError";
    this.kind = kind;
    this.status = options.status ?? null;
    this.code = options.code ?? null;
    this.requestId = options.requestId ?? null;
    this.retryable = options.retryable ?? false;
  }
}

export function createMemoryCredentialStore() {
  const store = Object.freeze({
    clear() {
      credentialValues.set(store, null);
    },
    set(value) {
      if (typeof value !== "string" || value.length === 0) {
        throw new TypeError("A non-empty bearer credential is required.");
      }
      credentialValues.set(store, value);
    },
  });
  credentialValues.set(store, null);
  return store;
}

const staleSession = () =>
  new ApiClientError("stale_session", "The session changed before this response applied.");

// One session per origin and profile, held by a SharedWorker (ADR-009). The page never reads
// the key back: it keeps this state, whose token changes on every accepted change.
export function connectSharedSession({ pingTimeoutMs = 3000 } = {}) {
  const listeners = new Set();
  const pending = new Map();
  let state = Object.freeze({ token: null, phase: "connecting", principalId: null, reason: null });
  let sequence = 0;
  let port = null;
  let pingTimer = null;
  let misses = 0;

  function emit({ token, phase, principalId, reason }) {
    state = Object.freeze({ token, phase, principalId, reason });
    listeners.forEach((listener) => listener(state));
  }

  function settle({ id, token, refused, network, status, headers, body }) {
    const entry = pending.get(id);
    pending.delete(id);
    const failure = (kind, message) => new ApiClientError(kind, message, { retryable: !!network });
    const empty = [204, 205, 304].includes(status);
    if (token !== state.token || refused === "stale_session") entry?.reject(staleSession());
    else if (refused) entry?.reject(failure("not_allowed", "The session refused this request."));
    else if (network) entry?.reject(failure("network", "The API could not be reached."));
    else entry?.resolve(new Response(empty ? null : body, { status, headers }));
  }

  // Pending requests of a lost or unusable worker never settle as success or error.
  function abandon(phase, reason) {
    clearTimeout(pingTimer);
    pingTimer = null;
    pending.forEach((entry) => entry.reject(staleSession()));
    pending.clear();
    emit({ token: null, phase, principalId: null, reason });
  }

  function connect() {
    port?.close();
    const worker = new SharedWorker("/public/api/session-worker.js", { name: "sre-agent-session" });
    worker.onerror = () => abandon("blocked", "worker_failed");
    port = worker.port;
    port.onmessage = ({ data }) => {
      if (data?.type === "pong") {
        clearTimeout(pingTimer);
        pingTimer = null;
        misses = 0;
      } else if (data?.type === "session") emit(data);
      else if (data?.type === "response") settle(data);
      else if (data?.type === "hello" && data.version !== SESSION_PROTOCOL) {
        abandon("blocked", "version_mismatch");
      }
    };
    port.postMessage({ type: "hello", version: SESSION_PROTOCOL });
  }

  // A worker that misses a ping is lost: the page connects again, and a dead worker's replacement
  // starts anonymous. One that keeps missing (it failed to start) blocks the page.
  function ping() {
    if (pingTimer !== null || state.phase === "blocked") return;
    pingTimer = setTimeout(() => {
      misses += 1;
      if (misses > 2) return abandon("blocked", "worker_failed");
      abandon("connecting", "worker_lost");
      connect();
    }, pingTimeoutMs);
    port.postMessage({ type: "ping" });
  }

  const command = (message) => state.phase !== "blocked" && port.postMessage(message);

  const session = Object.freeze({
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
      command({ type: "set", credential: value });
    },
    logout() {
      command({ type: "logout" });
    },
    retry() {
      command({ type: "retry" });
    },
  });
  sessionSenders.set(session, (token, path, { method, headers, body }) => {
    if (state.phase === "blocked") return Promise.reject(staleSession());
    return new Promise((resolve, reject) => {
      sequence += 1;
      pending.set(sequence, { resolve, reject });
      const message = { type: "request", id: sequence, token, path, method, body };
      port.postMessage({ ...message, headers: Object.fromEntries(headers) });
      ping();
    });
  });
  setInterval(ping, 10_000);
  connect();
  return session;
}

export function apiBaseUrlFrom(runtime = globalThis) {
  const configured = runtime.__SRE_AGENT_CONFIG__?.apiBaseUrl ?? "/api";
  const origin = runtime.location?.origin;
  if (typeof configured !== "string" || typeof origin !== "string" || configured.includes("\\")) {
    throw new TypeError("apiBaseUrl must be a same-origin absolute path.");
  }
  let resolved;
  try {
    resolved = new URL(configured, origin);
  } catch {
    throw new TypeError("apiBaseUrl must be a same-origin absolute path.");
  }
  if (
    !configured.startsWith("/") ||
    configured.startsWith("//") ||
    resolved.origin !== origin ||
    resolved.username ||
    resolved.password ||
    resolved.search ||
    resolved.hash
  ) {
    throw new TypeError("apiBaseUrl must be a same-origin absolute path.");
  }
  return resolved.pathname.replace(/\/$/, "");
}

function normalizedError(status, payload) {
  const detail = payload && typeof payload === "object" ? payload.error : null;
  const message =
    detail && typeof detail.message === "string" ? detail.message : `API request failed (${status}).`;

  return new ApiClientError(STATUS_KINDS[status] ?? "api", message, {
    status,
    code: detail && typeof detail.code === "string" ? detail.code : null,
    requestId:
      payload && typeof payload.request_id === "string" ? payload.request_id : null,
    retryable: payload?.retryable === true,
  });
}

async function responsePayload(response) {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) throw new TypeError("The API response body is empty.");
  try {
    return JSON.parse(text);
  } catch (cause) {
    throw new TypeError("The API response body is not valid JSON.", { cause });
  }
}

function mutationHeaders(idempotencyKey) {
  return idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {};
}

export function createAdministrativeApiClient({
  baseUrl = apiBaseUrlFrom(),
  credentialStore = createMemoryCredentialStore(),
  fetchImplementation = globalThis.fetch?.bind(globalThis),
  session,
} = {}) {
  if (typeof fetchImplementation !== "function") {
    throw new TypeError("A fetch implementation is required.");
  }
  if (!credentialValues.has(credentialStore)) {
    throw new TypeError("credentialStore must be created by createMemoryCredentialStore.");
  }
  const send = session === undefined ? null : sessionSenders.get(session);
  if (session !== undefined && !send) {
    throw new TypeError("session must be created by connectSharedSession.");
  }
  const normalizedBaseUrl = apiBaseUrlFrom({
    __SRE_AGENT_CONFIG__: { apiBaseUrl: baseUrl },
    location: globalThis.location,
  });

  async function request(path, { method = "GET", body, headers = {} } = {}) {
    const credential = credentialValues.get(credentialStore);
    const requestHeaders = new Headers({ Accept: "application/json", ...headers });
    if (body !== undefined) requestHeaders.set("Content-Type", "application/json");
    if (credential) requestHeaders.set("Authorization", `Bearer ${credential}`);
    const token = session?.state.token;
    const transport = send ? (_, init) => send(token, path, init) : fetchImplementation;

    let response;
    try {
      response = await transport(`${normalizedBaseUrl}${path}`, {
        method,
        headers: requestHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        referrerPolicy: "same-origin",
      });
    } catch (cause) {
      if (cause instanceof ApiClientError) throw cause;
      throw new ApiClientError("network", "The API could not be reached.", {
        cause,
        retryable: true,
      });
    }

    let payload;
    let invalid = null;
    try {
      payload = await responsePayload(response);
    } catch (cause) {
      invalid = cause;
    }
    if (send && session.state.token !== token) throw staleSession();
    if (invalid) {
      throw new ApiClientError("invalid_response", "The API returned an invalid response.", {
        cause: invalid,
        status: response.status,
        retryable: true,
      });
    }
    if (!response.ok) throw normalizedError(response.status, payload);
    return payload;
  }

  return Object.freeze({
    credentialStore,
    createPrincipal(body, idempotencyKey) {
      return request("/v1/principals", {
        method: "POST",
        body,
        headers: mutationHeaders(idempotencyKey),
      });
    },
    getPrincipal(principalId) {
      return request(`/v1/principals/${encodeURIComponent(principalId)}`);
    },
    issueCredential(principalId, body, idempotencyKey) {
      return request(`/v1/principals/${encodeURIComponent(principalId)}/credentials`, {
        method: "POST",
        body,
        headers: mutationHeaders(idempotencyKey),
      });
    },
    listCredentials(principalId) {
      return request(`/v1/principals/${encodeURIComponent(principalId)}/credentials`);
    },
    listPrincipals({ limit = 100 } = {}) {
      return request(`/v1/principals?limit=${encodeURIComponent(limit)}`);
    },
    listGrants({ principalId, resourceId, limit = 100 } = {}) {
      const hasPrincipal =
        principalId !== undefined && principalId !== null && principalId !== "";
      const hasResource =
        resourceId !== undefined && resourceId !== null && resourceId !== "";
      if (hasPrincipal === hasResource) {
        throw new TypeError("Exactly one of principalId or resourceId is required.");
      }
      const params = new URLSearchParams();
      if (hasPrincipal) params.set("principal_id", principalId);
      else params.set("resource_id", resourceId);
      params.set("limit", String(limit));
      return request(`/v1/grants?${params.toString()}`);
    },
    createGrant(body, idempotencyKey) {
      return request("/v1/grants", {
        method: "POST",
        body,
        headers: mutationHeaders(idempotencyKey),
      });
    },
    readUsageConsumption({ requestId, incidentId, month } = {}) {
      const hasRequest = requestId !== undefined && requestId !== null && requestId !== "";
      const hasIncident =
        incidentId !== undefined && incidentId !== null && incidentId !== "";
      const hasMonth = month !== undefined && month !== null && month !== "";
      if (Number(hasRequest) + Number(hasIncident) + Number(hasMonth) !== 1) {
        throw new TypeError("Exactly one of requestId, incidentId or month is required.");
      }
      const params = new URLSearchParams();
      if (hasRequest) params.set("request_id", requestId);
      else if (hasIncident) params.set("incident_id", incidentId);
      else params.set("month", month);
      return request(`/v1/usage/consumption?${params.toString()}`);
    },
    readUsageRequests({ requestId, incidentId, month } = {}) {
      const hasRequest = requestId !== undefined && requestId !== null && requestId !== "";
      const hasIncident =
        incidentId !== undefined && incidentId !== null && incidentId !== "";
      const hasMonth = month !== undefined && month !== null && month !== "";
      if (Number(hasRequest) + Number(hasIncident) + Number(hasMonth) !== 1) {
        throw new TypeError("Exactly one of requestId, incidentId or month is required.");
      }
      const params = new URLSearchParams();
      if (hasRequest) params.set("request_id", requestId);
      else if (hasIncident) params.set("incident_id", incidentId);
      else params.set("month", month);
      return request(`/v1/usage/requests?${params.toString()}`);
    },
    revokeGrant(grantId) {
      return request(`/v1/grants/${encodeURIComponent(grantId)}`, {
        method: "DELETE",
      });
    },
    listCatalogResources(
      { resourceType, ownerId, status, visibility, limit = 100 } = {},
    ) {
      const params = new URLSearchParams();
      if (resourceType) params.set("resource_type", resourceType);
      if (ownerId) params.set("owner_id", ownerId);
      if (status) params.set("status", status);
      if (visibility) params.set("visibility", visibility);
      params.set("limit", String(limit));
      return request(`/v1/catalog/resources?${params.toString()}`);
    },
    listModelAliases({ limit = 100 } = {}) {
      const query = limit === undefined ? "" : `?limit=${encodeURIComponent(String(limit))}`;
      return request(`/v1/model-aliases${query}`);
    },
    getModelAlias(modelAliasId) {
      return request(`/v1/model-aliases/${encodeURIComponent(modelAliasId)}`);
    },
    replaceModelAliasAssignment(modelAliasId, body) {
      return request(`/v1/model-aliases/${encodeURIComponent(modelAliasId)}/assignment`, {
        method: "PUT",
        body,
      });
    },
    replaceModelAliasStatus(modelAliasId, body) {
      return request(`/v1/model-aliases/${encodeURIComponent(modelAliasId)}/status`, {
        method: "PUT",
        body,
      });
    },
    replacePrincipalStatus(principalId, body) {
      return request(`/v1/principals/${encodeURIComponent(principalId)}/status`, {
        method: "PUT",
        body,
      });
    },
    revokeCredential(credentialId) {
      return request(`/v1/credentials/${encodeURIComponent(credentialId)}`, {
        method: "DELETE",
      });
    },
    rotateCredential(credentialId, body, idempotencyKey) {
      return request(`/v1/credentials/${encodeURIComponent(credentialId)}/rotation`, {
        method: "POST",
        body,
        headers: mutationHeaders(idempotencyKey),
      });
    },
    listAuditEvents({ principal_id, decision, model_alias_id, request_id, incident_id,
      run_id, task_id, trace_id, from, to, limit = 100 } = {}) {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries({ principal_id, decision, model_alias_id,
        request_id, incident_id, run_id, task_id, trace_id, from, to, limit })) {
        if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
      }
      if (!params.has("limit")) params.set("limit", "100");
      const query = params.toString();
      return request(`/v1/audit-events${query ? `?${query}` : ""}`);
    },
    getAuditEvent(eventId) {
      return request(`/v1/audit-events/${encodeURIComponent(eventId)}`);
    },
    getIncident(incidentId) {
      return request(`/v1/incidents/${encodeURIComponent(incidentId)}`);
    },
    getWhoAmI() {
      return request("/v1/whoami");
    },
    postTriageCommand(alertId, body, idempotencyKey) {
      return request(`/v1/alerts/${encodeURIComponent(alertId)}/triage/commands`, {
        method: "POST",
        body,
        headers: mutationHeaders(idempotencyKey),
      });
    },
    getTriageState(alertId) {
      return request(`/v1/alerts/${encodeURIComponent(alertId)}/triage`);
    },
    getTriageContext(alertId) {
      return request(`/v1/alerts/${encodeURIComponent(alertId)}/triage/context`);
    },
    getEligibleIncidents(alertId) {
      return request(`/v1/alerts/${encodeURIComponent(alertId)}/triage/eligible-incidents`);
    },
    getIncidentTimeline(incidentId, { runId, after, limit } = {}) {
      const params = new URLSearchParams();
      if (runId) params.set("run_id", runId);
      if (after) params.set("after", after);
      if (limit !== undefined) params.set("limit", String(limit));
      const query = params.toString();
      return request(
        `/v1/incidents/${encodeURIComponent(incidentId)}/timeline${query ? `?${query}` : ""}`,
      );
    },
    getIncidentSnapshot(incidentId, { runId } = {}) {
      const params = new URLSearchParams();
      if (runId) params.set("run_id", runId);
      const query = params.toString();
      return request(
        `/v1/incidents/${encodeURIComponent(incidentId)}/snapshot${query ? `?${query}` : ""}`,
      );
    },
    sendRunCommand(incidentId, runId, body, idempotencyKey) {
      return request(
        `/v1/incidents/${encodeURIComponent(incidentId)}/runs/${encodeURIComponent(runId)}/commands`,
        {
          method: "POST",
          body,
          headers: mutationHeaders(idempotencyKey),
        },
      );
    },
  });
}
