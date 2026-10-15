// The browser session of this origin and profile (ADR-009): the API key lives only here.
importScripts("/public/api/runtime-config.js");

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
    [phase, reason, principalId] = ["active", null, identity.principal_id];
    publish();
  } else if (response?.status === 401) {
    change("anonymous", "invalid_credential");
  } else {
    reason = "unreachable";
    publish();
  }
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
      ports.add(port);
      port.postMessage(snapshot());
    } else if (!ports.has(port)) {
      return;
    } else if (data?.type === "request") {
      forward(port, data);
    } else if (data?.type === "logout") {
      change("anonymous", "logout");
    } else if (data?.type === "set" && typeof data.credential === "string" && data.credential) {
      change("validating", null, data.credential);
      validate();
    }
  };
};
