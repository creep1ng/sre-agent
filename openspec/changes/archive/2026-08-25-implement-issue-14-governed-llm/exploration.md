## Exploration: Issue #14 governed LLM vertical slice

### Current State

`feat/issue-14-governed-llm` is clean and points at `6dc5e3a`, the same commit as
`origin/main`; dependencies #9, #11, and #13 are therefore present in this tree. The repository now
has a FastAPI composition root, PostgreSQL/Alembic persistence, deterministic principals and API
keys, the logical `triage-agent` LLM resource, an incident-harness-only active `invoke` grant, a
uniform bearer-authentication dependency, and append-only `AuditEvent` storage. The API currently
exposes health routes only. There is no `/v1/responses` route, provider port/adapter, request/response
runtime DTO, alias-resolution repository method, audit-reference/redaction producer, request timer,
or provider configuration.

The existing persistence is close to the required governance path but deliberately projects away
routing data. `ResourceRepository.get()` returns only `resource_type/resource_id`, while the
`resources` row also owns `status`, `alias`, `concrete_model`, `router`, and
`inference_provider`. `GrantRepository.decide()` already proves default deny, including
`restricted-harness`, and `AuditRepository.append()` flushes a strict HT-01 event inside a
caller-owned transaction. The endpoint must add two distinct reads: authorization-safe logical
resource lookup and post-allow model assignment resolution. Routing fields must not be loaded or
sent upstream on the deny path.

HT-01 release 1.1.0 already fixes the closed text-only request/response shapes, 422 -> 401 -> 403
ordering, indistinguishable 403 `resource_unavailable`, 502/503/504 upstream taxonomy, HMAC audit
references, and durable audit acceptance before releasing an ordinary result. Audit fields store
`request_id` directly under correlation and store alias, effective model, provider, Principal,
resource, and grant/policy as HMAC references; raw source identifiers would violate ADR-005. One
acceptance gap is real: neither the 1.1.0 `AuditEvent` schema/DTO nor `audit_events` table has a
latency field, so issue #14's “each attempt records latency” criterion cannot be met through the
common audit contract without an additive contract and migration change.

OpenRouter's current API exposes non-streaming `POST /api/v1/responses`, accepts provider routing
preferences, and exposes routing evidence on successful Responses calls when
`X-OpenRouter-Metadata: enabled` is sent. Its provider routing supports an allow-list and disabling
fallbacks. That fits this slice: send the concrete seeded model, restrict routing to the configured
provider, set `allow_fallbacks=false`, and validate exactly one selected provider from
`openrouter_metadata`. Missing, malformed, or contradictory evidence maps to the existing safe 502
`provider_evidence_invalid`; no generation lookup is needed for the normal path. Sources:
https://openrouter.ai/docs/api/api-reference/responses/create-responses,
https://openrouter.ai/docs/guides/features/router-metadata, and
https://openrouter.ai/docs/guides/routing/provider-selection.

The current Compose harness validates versioned contract fixtures from read-only inputs; it does not
call the API or count provider requests. PostgreSQL-backed pytest is already the strongest executable
pattern for this slice. A deterministic test double is necessary to prove “no upstream call”; a live
provider's absence of traffic cannot be proven reliably from client-side success/failure alone.

### Affected Areas

- `schemas/releases/*`, `schemas/tooling/*`, and `src/sre_agent/governance/dto.py` — publish a new
  additive audit latency field and issue-14 conformance obligation without mutating old releases.
- `migrations/versions/*`, `src/sre_agent/persistence/models.py`, and
  `src/sre_agent/persistence/repositories.py` — add non-null runtime latency persistence, safe logical
  alias lookup, post-allow assignment resolution, and durable event append behavior.
- `src/sre_agent/gateway/` — add strict Responses transport DTOs, request correlation/error mapping,
  authorization orchestration, provider port/adapter, normalization, and audit projection.
- `src/sre_agent/settings.py` and `src/sre_agent/application.py` — compose provider/audit settings and
  injectable ports without constructing SDK objects inside route handlers.
- `pyproject.toml` and `uv.lock` — promote an async HTTP client to a pinned runtime dependency; keep
  the OpenAI client test-only if it is used to prove public compatibility.
- `.env.example`, `compose.yaml`, and `docker/api.Dockerfile` — pass provider and audit secrets only to
  the API process and keep harness/client containers unaware of provider credentials.
- `tests/` — add contract-ordering, allow, deny/no-call, provider-failure, durable-audit-gate,
  normalization, and optional live-provider coverage with real PostgreSQL.
- `.github/workflows/ci.yml`, `README.md`, and `docs/architecture.md` — document deterministic and
  secret-gated live verification and ensure failure logs cannot print Authorization or provider
  payloads.

### Approaches

1. **Narrow provider port plus direct async HTTP adapter** — define an application-owned
   `LLMProvider` protocol and implement only OpenRouter Responses with a pinned `httpx.AsyncClient`.
   - Pros: explicit no-retry behavior and timeouts; direct access to response headers/router metadata;
     easy `MockTransport` or recording-adapter injection; smallest provider-native surface; HT-01
     normalization stays outside third-party DTOs.
   - Cons: request/response validation and safe error mapping are application code; `httpx` must move
     from dev-only to runtime dependencies.
   - Effort: Medium

2. **Official OpenRouter Python SDK behind the same port** — use its generated Responses API types and
   disable SDK retries.
   - Pros: provider-specific request types and error classes are maintained upstream; metadata opt-in
     is first-class.
   - Cons: larger and faster-moving dependency surface; generated streaming/event abstractions are
     unnecessary for this non-streaming slice; transport injection and exact raw evidence handling are
     less transparent; SDK retry defaults must be proven disabled.
   - Effort: Medium

3. **OpenAI Python SDK as the upstream adapter** — point `AsyncOpenAI` at OpenRouter and pass provider
   options/metadata headers as extras.
   - Pros: familiar Responses API and demonstrates ecosystem compatibility.
   - Cons: OpenRouter-specific provider selection and evidence become untyped escape hatches; raw
     response/header access is awkward; using OpenAI SDK types internally risks coupling the governed
     boundary to a client compatibility library.
   - Effort: Medium

### Recommendation

Use approach 1, while using the OpenAI Python SDK only as a black-box integration client against the
gateway. Public client compatibility and upstream adapter choice are separate concerns.

Implement the orchestration in this order: validate and assign one server `request_id`; authenticate
to `PrincipalContext`; load only logical resource identity/status; decide
`(principal, invoke, llm_model, alias)`; on deny, durably append the deny event and return uniform 403;
only after allow, resolve the active `ModelAlias`, call the provider once, validate provider evidence
and text, build the normalized HT-01 response, durably append the terminal event, and then release the
ordinary response. Measure elapsed monotonic time from request entry to terminal decision/upstream
normalization and store integer `latency_ms` on every persisted attempt. Never hold a database
transaction open across the network call.

Add `latency_ms` through a new immutable full contract release as an optional additive schema field,
make it mandatory in the issue-14 conformance consumer, and make the runtime database column non-null.
This preserves older release instances while giving the common audit projection a portable duration;
an internal DB-only column is not recommended because API/control-plane projections would silently
lose a required audit dimension.

Keep the first slice metadata-only: do not persist prompts or model output, do not log provider bodies,
and construct only `content_state=absent` audit events with HMAC-projected source identifiers. Read
`OPENROUTER_API_KEY` and `AUDIT_HMAC_KEY` from the API environment only. The client receives only an
incident/restricted harness key; neither response, audit, exception, test output, nor container logs
may contain provider credentials.

Verification should have two layers:

1. Default CI/Compose runs PostgreSQL-backed endpoint tests with an injected recording adapter or
   `httpx.MockTransport`. The allow test asserts one upstream call with the concrete model; the deny
   test snapshots the call count at zero and queries the committed deny audit. Provider exception and
   malformed-body cases prove HT-01 502/503/504 mapping and committed failure audits.
2. A separately named, explicit live smoke test calls the full gateway with the OpenAI SDK and an
   operator/CI-secret `OPENROUTER_API_KEY`, using the configured `TRIAGE_AGENT_MODEL/PROVIDER`. It is
   skipped when the secret is absent, makes one bounded non-streaming request, and asserts only the
   normalized response and protected audit dimensions. This proves the real adapter without making
   ordinary CI flaky or distributing the provider credential to the client/harness.

Provider automatic retries and fallback must be disabled. HTTP timeout becomes safe retryable 504;
temporary route/transport availability becomes safe retryable 503; malformed, contradictory, or
unadaptable success/error evidence becomes non-retryable 502. `Retry-After` is forwarded only after
strictly validating a reliable bounded value. Audit-store failure suppresses the intended 200/403 or
normalized provider error and returns safe retryable 503 `audit_unavailable`.

### Risks

- Latency is absent from HT-01 1.1.0; implementing code first would either miss acceptance or create an
  undocumented DB-only contract fork.
- The current global FastAPI validation and authentication handlers return 422/401 without durable
  audit. The proposal/spec must decide them explicitly against HT-01's “every outcome” release gate;
  they must not be silently treated as compliant because the two headline scenarios pass.
- `ResourceRepository.get()` discards route assignment and status, while selecting the whole row too
  early would violate authorize-before-routing. Separate query/projection methods are required.
- OpenRouter metadata is external and evolving. Admit only the bounded fields needed to identify one
  selected provider; never persist the full metadata object.
- A remote live test is not deterministic and can incur cost, rate limits, or model/provider drift.
  It supplements, never replaces, the recording-adapter integration suite.
- Holding a SQL transaction/session across provider I/O can exhaust the pool and create ambiguous
  audit commits. Network work must occur between short governance-read and audit-append transactions.
- The work likely exceeds the 400-line review budget because contract evolution, migration, runtime,
  and integration evidence are distinct concerns. Plan reviewable slices before apply under the
  `ask-on-risk` delivery strategy.

### Ready for Proposal

Yes. The proposal should lock the direct HTTP provider port, single-provider/no-fallback request,
bounded router-metadata evidence, additive `latency_ms` contract path, durable audit release ordering,
metadata-only audit scope, deterministic no-call proof, and separate secret-gated live smoke test.
