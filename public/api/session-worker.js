// The browser session of this origin and profile (ADR-009): the API key lives only here.
importScripts("/public/api/runtime-config.js");

const PROTOCOL = 1;
// ADR-009, section 6: when a page connects or becomes visible again, an active session whose last
// validation is older than this is checked again with whoami.
const REVALIDATE_AFTER_MS = 60_000;
const METHODS = new Set(["GET", "POST", "PUT", "DELETE"]);
const HEADERS = new Set(["accept", "content-type", "idempotency-key"]);
const PATH = /^\/v1\/[\w\-.~!*'()%/]*(\?[\w\-.~!*'()%=&+]*)?$/;
const ESCAPES = /\.\.|\/\/|%2e|%2f|%5c/i;
const configured = globalThis.__SRE_AGENT_CONFIG__?.apiBaseUrl ?? "/api";
if (typeof configured !== "string" || !/^\/(?!\/)[^\\?#]*$/.test(configured)) {
  throw new TypeError("apiBaseUrl must be a same-origin absolute path.");
}
const apiBase = new URL(configured, self.location.origin).pathname.replace(/\/$/, "");
// getRandomValues, unlike randomUUID, also works on plain-HTTP origins such as http://web.
const instance = crypto.getRandomValues(new Uint32Array(4)).join("-");
const ports = new Set();
let counter = 0;
let phase = "anonymous";
let reason = null;
let principalId = null;
let credential = null;
let validatedAt = 0;
let revalidating = false;

const token = () => `${instance}:${counter}`;
const snapshot = () => ({ type: "session", token: token(), phase, principalId, reason });
const publish = () => ports.forEach((port) => port.postMessage(snapshot()));

// Every accepted change is a new generation, published before anything is validated.
function change(nextPhase, nextReason, nextCredential = null) {
  counter += 1;
  [phase, reason, principalId, credential] = [nextPhase, nextReason, null, nextCredential];
  publish();
}

function call(path, { method = "GET", headers = { accept: "application/json" }, body } = {}) {
  return fetch(`${apiBase}${path}`, {
    method,
    headers: { ...headers, authorization: `Bearer ${credential}` },
    body,
    cache: "no-store",
    credentials: "omit",
    redirect: "error",
    referrerPolicy: "same-origin",
  });
}

// A validation applies only while its generation is current; a later change always wins.
async function validate() {
  const generation = counter;
  const response = await call("/v1/whoami").catch(() => null);
  const identity = response?.status === 200 ? await response.json().catch(() => null) : null;
  if (generation !== counter) return;
  if (typeof identity?.principal_id === "string") {
    [phase, reason, principalId, validatedAt] = ["active", null, identity.principal_id, Date.now()];
    publish();
  } else if (response?.status === 401) {
    change("anonymous", "invalid_credential");
  } else if (phase === "validating") {
    reason = "unreachable";
    publish();
  }
}

// A revoked key is found at the next request or revalidation, never at once. A revalidation that
// cannot reach the API leaves the session as it is, and the next connection or visit tries again.
async function revalidate() {
  if (phase !== "active" || revalidating || Date.now() - validatedAt <= REVALIDATE_AFTER_MS) return;
  revalidating = true;
  const generation = counter;
  const response = await call("/v1/whoami").catch(() => null);
  revalidating = false;
  if (generation !== counter) return;
  if (response?.status === 200) validatedAt = Date.now();
  else if (response?.status === 401) change("anonymous", "credential_rejected");
}

const permitted = ({ path, method, headers, body }) =>
  typeof path === "string" &&
  PATH.test(path) &&
  !ESCAPES.test(path) &&
  METHODS.has(method) &&
  typeof headers === "object" &&
  headers !== null &&
  Object.entries(headers).every(([key, value]) => HEADERS.has(key) && typeof value === "string") &&
  (body === undefined || typeof body === "string");

async function forward(port, message) {
  const reply = (fields) =>
    port.postMessage({ type: "response", id: message.id, token: message.token, ...fields });
  if (message.token !== token() || phase !== "active") return reply({ refused: "stale_session" });
  if (!permitted(message)) return reply({ refused: "not_allowed" });
  const generation = counter;
  try {
    const response = await call(message.path, message);
    const body = await response.text();
    if (response.status === 401 && generation === counter) {
      change("anonymous", "credential_rejected");
    }
    reply({ status: response.status, headers: [...response.headers], body });
  } catch {
    reply({ network: true });
  }
}

onconnect = ({ ports: [port] }) => {
  port.onmessage = ({ data }) => {
    if (data?.type === "hello") {
      port.postMessage({ type: "hello", version: PROTOCOL });
      // A newer page means a newer deploy: this worker steps down and its key goes with it.
      if (data.version > PROTOCOL) close();
      if (data.version !== PROTOCOL) return;
      ports.add(port);
      port.postMessage(snapshot());
      revalidate();
    } else if (!ports.has(port)) {
      // A page of another version gets no session: its requests are refused, nothing else runs.
      if (data?.type === "request") forward(port, { ...data, token: null });
    } else if (data?.type === "ping") {
      port.postMessage({ type: "pong" });
    } else if (data?.type === "visible") {
      revalidate();
    } else if (data?.type === "request") {
      forward(port, data);
    } else if (data?.type === "logout") {
      change("anonymous", "logout");
    } else if (data?.type === "set" && typeof data.credential === "string" && data.credential) {
      change("validating", null, data.credential);
      validate();
    } else if (data?.type === "retry" && phase === "validating") {
      reason = null;
      publish();
      validate();
    }
  };
};
