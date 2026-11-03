import { useLive } from "./live";

/*
 * Same-origin calls to the governed control plane with the credential of the console's session.
 * Every answer is reduced to a kind the page can explain; server codes and messages never reach
 * the screen.
 */

export type AdminError =
  | "network"
  | "auth"
  | "forbidden"
  | "missing"
  | "conflict"
  | "invalid"
  | "too_large"
  | "unavailable";

export type AdminResult<T> = { ok: true; body: T } | { ok: false; error: AdminError };

export interface Page<T> {
  items: T[];
  truncated?: boolean;
}

export type PrincipalKind = "human" | "agent";

export interface Principal {
  principal_id: string;
  kind: PrincipalKind;
  display_name: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Credential {
  credential_id: string;
  prefix: string;
  status: string;
  created_at: string;
  expires_at?: string | null;
  revoked_at?: string | null;
}

export interface IssuedCredential {
  key?: string;
  secret_revealed?: boolean;
}

/** A rotation revokes the old key and issues its replacement in one transaction. */
export interface CredentialRotation {
  old_credential: Credential;
  issuance: IssuedCredential & { credential: Credential };
}

export interface ResourceRef {
  resource_type: string;
  resource_id: string;
}

export interface Grant {
  grant_id: string;
  principal_id: string;
  action: string;
  resource: ResourceRef;
  status: string;
}

export interface CatalogResource extends ResourceRef {
  status: string;
  source?: string;
  discoverability?: { display_name?: string } | null;
}

export interface SkillDependency {
  skill_id: string;
  version: string;
}

export interface SkillManifest {
  display_name: string;
  description: string;
  instructions: string;
  dependencies: SkillDependency[];
}

/** One immutable Skill version, as the owner published it. */
export interface SkillVersion {
  skill_id: string;
  version: string;
  owner_id: string;
  resource_id: string;
  manifest: SkillManifest;
  content_sha256: string;
  created_at: string;
}

export interface SkillStatus {
  resource_id: string;
  status: "active" | "inactive";
  updated_at: string;
}

export interface BoKChunk {
  section_id: string;
  chunk_index: number;
  content: string;
}

export interface BoKDocument {
  document_id: string;
  title: string;
  source_ref: string;
  chunks: BoKChunk[];
}

export interface BoKVersion {
  resource_id: string;
  collection_id: string;
  version: string;
  owner_id: string;
  display_name: string;
  description: string;
  status: string;
  document_count: number;
  chunk_count: number;
  published_by?: string | null;
  origin?: string | null;
  documents?: BoKDocument[];
}

export interface BoKSearchResult {
  document_id: string;
  section_id: string;
  chunk_index: number;
  title: string;
  source_ref: string;
  content: string;
  score: number;
}

export interface ModelAlias {
  model_alias_id: string;
  alias: string;
  concrete_model: string;
  router: string;
  inference_provider: string;
  status: string;
  updated_at: string;
}

export interface ConsumptionLimits {
  version: number;
  incident_token_limit: number | null;
  monthly_usd_limit: string | number | null;
  updated_at: string | null;
}

export type ConsumptionFilter = { request_id: string } | { incident_id: string } | { month: string };

export interface ConsumptionSummary {
  request_count: number | null;
  incident_runs: number | null;
  totals?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
    cost?: { amount?: string | number | null; price_versions?: string[] };
  };
  coverage?: { status?: string; known?: number | null; incomplete?: number | null; unknown?: number | null };
  filter?: { month?: string };
}

export interface Availability {
  availability?: string;
  value?: string | null;
}

export interface UsageRequest {
  request_id: string;
  month?: string | null;
  attribution_status?: string;
  requested_assignment?: {
    availability?: string;
    alias?: string | null;
    model?: string | null;
    provider?: string | null;
    router?: string | null;
  };
  credited_model?: Availability;
  credited_provider?: Availability;
  consumption?: {
    availability?: string;
    source?: string;
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
    billed_usd?: string | number | null;
    pricing_context?: { price_version?: string; observed_at?: string } | null;
  } | null;
}

export interface Digest {
  digest?: string;
}

export interface AuditEvent {
  event_id: string;
  occurred_at: string;
  operation?: string;
  action?: string;
  stage?: string;
  outcome?: string;
  reason_code?: string;
  response_status?: number;
  latency_ms?: number;
  identity?: { principal_kind?: string; principal_status?: string; principal_ref?: Digest };
  resource?: { resource_type?: string; resource_ref?: Digest };
  model_alias_ref?: Digest;
  routing?: { router?: string; model_ref?: Digest; provider_ref?: Digest } | null;
  policy_decision?: { decision?: string; reason_code?: string };
  authorization_denial_cause?: string;
  content_state?: string;
  correlation?: {
    request_id?: string;
    incident_ref?: Digest;
    run_ref?: Digest;
    task_ref?: Digest;
    trace_ref?: Digest;
  };
}

export type AuditFilters = Partial<
  Record<
    | "principal_id"
    | "decision"
    | "model_alias_id"
    | "request_id"
    | "incident_id"
    | "run_id"
    | "task_id"
    | "trace_id"
    | "from"
    | "to"
    | "limit",
    string
  >
>;

function errorOf(status: number): AdminError {
  if (status === 401) return "auth";
  if (status === 403) return "forbidden";
  if (status === 404) return "missing";
  if (status === 409 || status === 412) return "conflict";
  if (status === 400 || status === 422) return "invalid";
  if (status === 413) return "too_large";
  return "unavailable";
}

async function request<T>(
  path: string,
  { method = "GET", body, idempotencyKey }: { method?: string; body?: unknown; idempotencyKey?: string } = {},
): Promise<AdminResult<T>> {
  const token = useLive.getState().token;
  if (!token) return { ok: false, error: "auth" };
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
    });
  } catch {
    return { ok: false, error: "network" };
  }
  if (!response.ok) return { ok: false, error: errorOf(response.status) };
  if (response.status === 204) return { ok: true, body: undefined as T };
  try {
    return { ok: true, body: (await response.json()) as T };
  } catch {
    return { ok: false, error: "unavailable" };
  }
}

const id = encodeURIComponent;
const query = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  return search.toString();
};

/** A fresh key per mutation attempt; a retry of the same body reuses it. */
export function idempotencyKey(prefix: string): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `${prefix}-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export const adminApi = {
  listPrincipals: () => request<Page<Principal>>("/principals?limit=100"),
  getPrincipal: (principalId: string) => request<Principal>(`/principals/${id(principalId)}`),
  createPrincipal: (body: { principal_id: string; kind: PrincipalKind; display_name: string }, key: string) =>
    request<Principal>("/principals", { method: "POST", body, idempotencyKey: key }),
  deactivatePrincipal: (principalId: string, expectedUpdatedAt: string) =>
    request<Principal>(`/principals/${id(principalId)}/status`, {
      method: "PUT",
      body: { status: "inactive", expected_updated_at: expectedUpdatedAt },
    }),
  listCredentials: (principalId: string) => request<Page<Credential>>(`/principals/${id(principalId)}/credentials`),
  issueCredential: (principalId: string, body: { expires_at?: string }, key: string) =>
    request<IssuedCredential>(`/principals/${id(principalId)}/credentials`, { method: "POST", body, idempotencyKey: key }),
  revokeCredential: (credentialId: string) => request<undefined>(`/credentials/${id(credentialId)}`, { method: "DELETE" }),
  rotateCredential: (credentialId: string, body: { expires_at?: string }, key: string) =>
    request<CredentialRotation>(`/credentials/${id(credentialId)}/rotation`, { method: "POST", body, idempotencyKey: key }),

  listGrants: (filter: { principal_id: string } | { resource_id: string }) =>
    request<Page<Grant>>(`/grants?${query({ ...filter, limit: "100" })}`),
  createGrant: (body: { grant_id: string; principal_id: string; action: string; resource: ResourceRef }, key: string) =>
    request<Grant>("/grants", { method: "POST", body: { ...body, effect: "allow" }, idempotencyKey: key }),
  revokeGrant: (grantId: string) => request<unknown>(`/grants/${id(grantId)}`, { method: "DELETE" }),

  listCatalogResources: (status?: string) =>
    request<Page<CatalogResource>>(`/catalog/resources?${query({ status, limit: "100" })}`),
  whoami: () => request<{ principal_id: string }>("/whoami"),
  listSkills: () => request<Page<CatalogResource>>("/catalog/resources?resource_type=skill&limit=100"),
  getSkill: (skillId: string, version: string) => request<SkillVersion>(`/skills/${id(skillId)}/${id(version)}`),
  getSkillStatus: (skillId: string, version: string) =>
    request<SkillStatus>(`/skills/${id(skillId)}/${id(version)}/status`),
  publishSkill: (body: { skill_id: string; version: string; owner_id: string; manifest: SkillManifest }, key: string) =>
    request<SkillVersion>("/skills/versions", { method: "POST", body, idempotencyKey: key }),
  setSkillStatus: (skillId: string, version: string, status: "active" | "inactive", expectedUpdatedAt: string) =>
    request<SkillStatus>(`/skills/${id(skillId)}/${id(version)}/status`, {
      method: "PUT",
      body: { status, expected_updated_at: expectedUpdatedAt },
    }),
  listCollections: () => request<Page<CatalogResource>>("/catalog/resources?resource_type=bok_collection&limit=100"),
  getCollection: (collectionId: string, version: string) =>
    request<BoKVersion>(`/bok/collections/${id(collectionId)}/versions/${id(version)}`),
  publishCollection: (
    body: { collection_id: string; version: string; display_name: string; description: string; documents: BoKDocument[] },
    key: string,
  ) => request<BoKVersion>("/bok/collections/versions", { method: "POST", body, idempotencyKey: key }),
  searchCollection: (collectionId: string, version: string, query: string) =>
    request<{ results: BoKSearchResult[] }>(`/bok/collections/${id(collectionId)}/versions/${id(version)}/search`, {
      method: "POST",
      body: { query, limit: 5 },
    }),
  listModelAliases: () => request<Page<ModelAlias>>("/model-aliases?limit=100"),
  getModelAlias: (aliasId: string) => request<ModelAlias>(`/model-aliases/${id(aliasId)}`),
  replaceAssignment: (
    aliasId: string,
    body: { concrete_model: string; router: string; inference_provider: string; expected_updated_at: string },
  ) => request<ModelAlias>(`/model-aliases/${id(aliasId)}/assignment`, { method: "PUT", body }),
  deactivateAlias: (aliasId: string, expectedUpdatedAt: string) =>
    request<ModelAlias>(`/model-aliases/${id(aliasId)}/status`, {
      method: "PUT",
      body: { status: "inactive", expected_updated_at: expectedUpdatedAt },
    }),

  getLimits: () => request<ConsumptionLimits>("/consumption-limits"),
  replaceLimits: (
    body: { expected_version: number; incident_token_limit: number | null; monthly_usd_limit: string | null },
    key: string,
  ) => request<ConsumptionLimits>("/consumption-limits", { method: "PUT", body, idempotencyKey: key }),
  readConsumption: (filter: ConsumptionFilter) =>
    request<ConsumptionSummary>(`/usage/consumption?${query(filter as Record<string, string>)}`),
  readUsageRequests: (filter: ConsumptionFilter) =>
    request<Page<UsageRequest>>(`/usage/requests?${query(filter as Record<string, string>)}`),

  listAuditEvents: (filters: AuditFilters) =>
    request<Page<AuditEvent>>(`/audit-events?${query({ limit: "100", ...filters })}`),
  getAuditEvent: (eventId: string) => request<AuditEvent>(`/audit-events/${id(eventId)}`),
};

/** Mirror of GRANT_ADMITTED_ACTIONS in src/sre_agent/control/service.py: the API refuses any other pair. */
export const GRANT_ACTIONS: Record<string, readonly string[]> = {
  llm_model: ["admin.read", "admin.write", "invoke"],
  mcp_server: ["admin.write", "mcp.discovery", "mcp.invoke"],
  mcp_tool: ["admin.write", "mcp.discovery", "mcp.invoke"],
  skill: ["admin.write", "skill.discovery", "skill.read", "skill.invoke", "invoke"],
  bok_collection: ["admin.write", "bok.discovery", "bok.search", "bok.read"],
  incident_workflow: [
    "run.start",
    "run.read",
    "run.command",
    "run.approve",
    "run.read_context",
    "alert.read",
    "alert.triage",
    "alert.dismiss",
    "alert.associate",
    "incident.declare",
    "change.read",
    "change.write",
  ],
  administrative_control: ["admin.read", "admin.write"],
  service_operation: ["mitigation.execute"],
};

/** The seeded administrative resources: the catalog never lists them, yet grants target them. */
export const ADMIN_RESOURCES: readonly ResourceRef[] = [
  "principals",
  "credentials",
  "model_aliases",
  "usage",
  "consumption_limits",
  "catalog",
  "grants",
].map((resource_id) => ({ resource_type: "administrative_control", resource_id }));

/** A Skill id and its semantic version, as `POST /v1/skills/versions` validates them. */
export const SKILL_ID = /^[a-z][a-z0-9-]{2,62}[a-z0-9]$/;
export const SEMVER = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;

/** A BoK collection, document or section id, as the publish route validates it. */
export const BOK_SLUG = /^[a-z0-9][a-z0-9-]{0,99}$/;

export const SLUG = /^[a-z][a-z0-9_-]{2,63}$/;
export const CONCRETE_MODEL = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._:-]+$/;
export const TOKENS = /^(?:0|[1-9][0-9]{0,14})$/;
export const USD = /^(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,12})?$/;
