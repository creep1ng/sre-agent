const STATUS_KINDS = Object.freeze({
  401: "authentication",
  403: "authorization",
  404: "not_found",
  409: "conflict",
});
const credentialValues = new WeakMap();

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
} = {}) {
  if (typeof fetchImplementation !== "function") {
    throw new TypeError("A fetch implementation is required.");
  }
  if (!credentialValues.has(credentialStore)) {
    throw new TypeError("credentialStore must be created by createMemoryCredentialStore.");
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

    let response;
    try {
      response = await fetchImplementation(`${normalizedBaseUrl}${path}`, {
        method,
        headers: requestHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        referrerPolicy: "same-origin",
      });
    } catch (cause) {
      throw new ApiClientError("network", "The API could not be reached.", {
        cause,
        retryable: true,
      });
    }

    let payload;
    try {
      payload = await responsePayload(response);
    } catch (cause) {
      throw new ApiClientError("invalid_response", "The API returned an invalid response.", {
        cause,
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
  });
}
