# Design: Gateway boundary contracts and ADRs

## Technical approach

Publish immutable contracts, not a gateway. Standalone JSON Schema Draft 2020-12 owns domain/envelopes; canonical OpenAPI 3.1.0 under `/schemas` owns HTTP and references them. Future FastAPI output is a runtime projection, never authority; `info.version: 1.0.0` versions the package.

## Architecture decisions

| Topic | Choice and rationale | Rejected/tradeoff |
|---|---|---|
| Authority | Standalone closed schemas have immutable absolute `$id`; canonical OAS 3.1.0 uses external `$ref`. | OpenAPI-first harms non-HTTP reuse; duplication drifts. |
| Releases | Full immutable `releases/<SemVer>` snapshots; no symlink/`current`/overwritten `$id`. Consumers pin versions; `/v1` API major is manifest metadata. | Major-only paths lose patch/minor provenance; pointers are ambiguous. |
| Responses metadata | Flat string `metadata.requested_model_alias/router/inference_provider`. | Headers are proxy-sensitive; a top-level extension breaks SDK shape/unknown-field rules. |
| Tooling | Lockfile-pinned Node is development-only: Ajv validates Draft 2020-12 schemas/fixtures, not whole OpenAPI; Redocly CLI lint/bundles OAS and resolves refs, distinct from ReDoc. Python runtime stays separate. | Extra Node runtime; representation diffs can false-positive. Bundle/normalize first, compare semantics not order/format. |
| Runtime docs | FastAPI defaults to OAS 3.1.0; generated `/openapi.json` projects registered implementation. `/docs` Swagger UI and `/redoc` ReDoc consume it only after canonical semantic-diff and fixture gates. Never replace `app.openapi()` blindly; customization must derive from/verify `app.routes`. | Generated-first omits non-runtime artifacts; canonical injection could document unimplemented routes. |
| Provider success metadata | Send `X-OpenRouter-Metadata: enabled`. For a successful no-cache response carrying `openrouter_metadata`, require exactly one `endpoints.available[]` item with `selected:true`; map only its `provider` to `metadata.inference_provider` and AuditEvent, while retaining `router=openrouter`. | Missing, multiple, or unadaptable selected providers produce safe non-retryable 502; raw metadata never crosses the public boundary. |
| Provider success fallback | A successful response without `openrouter_metadata` must capture and validate exclusively the upstream `X-Generation-Id` header, then perform one bounded `GET /api/v1/generation` lookup keyed by that header value. The public Response body `id` SHALL NOT be used or confused as the generation lookup key. Continue only when the lookup resolves exactly one provider; missing/invalid header, lookup failure, ambiguity, or unadaptable metadata produces safe non-retryable 502. | Adds latency and a second failure mode. No unlimited retries; metadata absence alone is never classified as a cache hit without lookup evidence, and raw lookup metadata is never public or persisted without redaction. |
| Provider error | Upstream unavailable/no-route and timeout paths do not require a selected endpoint; preserve their normalized 503 and 504 taxonomy. Attempts/pipeline metadata may enter only redacted audit evidence and is never public. | Applying success-only selected-provider validation to errors would corrupt retry semantics. |
| Stage-aware audit | Every safe event has event/time, request UUID, closed operation/action/reason/stage/outcome/redaction vocabularies, and only audit-local evidence. Source identity/credential/resource/model/policy/grant/routing/correlation/untrusted values become domain-separated HMAC-SHA-256 `auditRef` envelopes over exact canonical UTF-8 bytes; schema owns closed shape while producers own vectors, canonicalization, domains, key versions, and key custody. | Canonical object reuse, raw strings, and recursive secret pattern guessing create sink surfaces; a single all-fields-required shape would fabricate pre-auth authority. |
| Redaction failure | Discard raw/partial content and form metadata-only `redaction_failed`; execution may continue only after that safe AuditEvent is durably accepted. | Rejecting all execution reduces leakage further but contradicts the specified safe metadata fallback and harms availability. |
| Audit acceptance | An abstract authoritative `AuditStore` must durably accept the redacted or metadata-only event before any ordinary success, deny, contract, or normalized upstream-error result is released. Rejection/unavailability suppresses that result and returns safe retryable 503 `audit_unavailable`; a sanitized operational signal is best-effort and must not claim persistence. Langfuse/exporters are downstream, so their later failure does not alter an already audited response. | This adds a release dependency but intentionally prescribes no DB/outbox implementation. |

## Package layout

```text
schemas/
  tooling/{package.json,package-lock.json,redocly.yaml,validate.mjs}
  adrs/{ADR-001-responses.md,ADR-002-principal.md,ADR-003-api-keys.md,
        ADR-004-grants.md,ADR-005-audit-redaction.md}
  releases/1.0.0/
    manifest.yaml
    openapi/{control-plane.yaml,responses.yaml}
    json-schema/domain/{principal,credential-reference,principal-context,
      model-alias,resource,grant,policy-decision,audit-event,correlation}.schema.json
    json-schema/http/{error-envelope,idempotency-record,bootstrap-seed,
      credential-issuance,responses-request,responses-response,list-envelope}.schema.json
    examples/{control-plane,responses,audit}/
    fixtures/{positive,negative}/
    conformance/{suite.yaml,consumers.yaml,ownership-matrix.yaml,evidence.json}
```

The manifest pins `contract_version`, `api_path_major`, dialects, `$id`s, ADR/evidence hashes, and baseline. Future `1.0.x`, `1.x`, and `2.x` are complete siblings; old releases remain.

```text
canonical schemas/OAS → Ajv(schemas/fixtures)+Redocly(OAS lint/bundle) → FastAPI /openapi.json → normalized semantic diff+fixtures → /docs,/redoc
```

The gate rejects missing/extra behavior. Canonical scope also owns standalone schemas, negative fixtures, ADRs, ownership, SemVer, and consumer conformance that FastAPI cannot generate.

## Interfaces and data flow

Control mappings:

```text
Principal: POST:/v1/principals=PrincipalCreate→Principal; GET:one/list=Principal/PrincipalList; PUT:status=StatusReplace→Principal
Credential: POST:issue/rotation=CredentialIssue|Rotate→CredentialIssuance; GET:list=CredentialList; DELETE=204
ModelAlias: POST:create=ModelAlias; GET:one/list=ModelAlias/ModelAliasList; PUT:assignment/status=ModelAlias
Grant: POST:create=Grant; GET:filtered-list=GrantList; DELETE=204
Audit: GET:one/filtered-list=metadata-only AuditEvent/AuditEventList projections; content fields/parameters are unsupported (422)
```

Lists emit `items,limit,truncated`; limit=100 default/max, no continuation. Grant/Audit require filters; excess remains unreachable until narrowed.

POST requires `Idempotency-Key`; `IdempotencyRecord` captures Principal+method+canonical-path/IDs+key-digest, RFC-8785 payload SHA-256, outcome, expiry. Normal records live >=24h; credential issue/rotation bindings last Principal lifetime, preventing post-revocation replay minting. Replays expose IDs/status with `secret_revealed=false`; bootstrap is fixture-only. `ErrorEnvelope` covers 400/401/403/404/409/422, audit-store 503 `audit_unavailable`, and normalized upstream 502/503/504; unknown fields→422. Upstream 502 is non-retryable; 503/504 are retryable; `audit_unavailable` remains distinct from upstream unavailable/no-route codes, and `Retry-After` requires a reliable estimate.

```mermaid
sequenceDiagram
  Client->>Gateway: validate body/trace; generate request_id
  alt validation fails
    Gateway->>Gateway: stage=validation 422; no identity/decision; body IDs untrusted
  else validation succeeds
    Gateway->>Authenticator: Bearer -> PrincipalContext
    alt authentication fails
      Authenticator-->>Gateway: stage=authentication 401; identity only if safely resolved
    else authentication succeeds
      Gateway->>Authorizer: invoke ModelAlias + bound domain IDs
      alt deny/missing/inactive
        Authorizer-->>Gateway: stage=authorization 403; no routing
      else allow
        Gateway->>Resolver: alias -> concrete model/router policy
        Resolver->>OpenRouter: concrete model; X-OpenRouter-Metadata: enabled
        OpenRouter-->>Normalizer: success/error + optional metadata and X-Generation-Id
        alt success with metadata (no-cache evidence)
          Normalizer->>Normalizer: require exactly one selected endpoint; map provider only
        else success without metadata (cache status unproven)
          Normalizer->>Normalizer: require valid X-Generation-Id; missing/invalid is safe 502
          Normalizer->>OpenRouter: one bounded GET /api/v1/generation keyed only by X-Generation-Id
          OpenRouter-->>Normalizer: exactly one provider or lookup failure/drift
          Normalizer->>Normalizer: one provider continues; otherwise safe 502
        else unavailable/no-route or timeout
          Normalizer->>Normalizer: preserve safe 503/504; no selected endpoint or lookup required
        end
        Normalizer-->>Gateway: stage=upstream normalized success or safe 502/503/504
      end
    end
  end
  Gateway->>Redactor: safe stage-aware intended result/audit candidate
  Redactor->>AuditStore: redacted or metadata-only event
  alt durably accepted
    AuditStore-->>Gateway: accepted
    Gateway-->>Client: intended success/deny/safe error
    AuditStore-->>Exporter: downstream sanitized export
  else rejected or unavailable
    AuditStore-->>Gateway: not accepted
    Gateway->>OperationalSignal: sanitized best-effort audit failure
    Gateway-->>Client: safe 503 audit_unavailable
  end
```

Future `Authenticator`, `Authorizer`, `AliasResolver`, `RouterAdapter`, `Normalizer`, `Redactor`, `AuditStore`, and exporter implementations/mappings live in consumers, not schemas. Router differs from inference provider; body domain IDs differ from server `request_id` and untrusted `traceparent`.

## Governance and conformance

ADRs follow Accepted/Context/Decision/Consequences/Alternatives/Deferred/Supersedes/links; 001 Responses/pre-route allow/OpenRouter, 002 single-workspace Principal, 003 Bearer/one-time secret, 004 direct allow/default deny, 005 stage-aware safe events/pre-sink redaction/durable authoritative acceptance/append-only audit. Normative ADRs are superseded, never rewritten. Git owns contracts/evidence; DB runtime records; secret stores deployment secrets. `AuditEvent` is vendor-neutral; Langfuse/exporters consume only accepted events downstream. The sink gate classifies source→removes structure→matches secrets→detects patterns→scans text, then emits policy/category/count plus `absent|redacted|redaction_failed`; raw data has no sink port. Correlation is Principal-bound, limited, non-authoritative.

Fixtures use `<plane>.<operation>.<case>.<positive|negative>.v1.0.0.json`; each names target/rule/status. Provider evidence distinguishes the public Response body `id` from upstream `X-Generation-Id`, and covers metadata success, bounded generation lookup, missing/invalid header, lookup drift/failure 502, and error-path 503/504 with neither selected endpoint nor lookup. Audit evidence covers stage-aware pre-auth 422/401, conditional authority dimensions, durable acceptance, authoritative-store 503, and downstream exporter failure. Goldens cover canonical bundle, normalized FastAPI projection/bodies, not tool text. Matrix: #10 transport; #11 schema mapping; #13 Bearer/context/401 plus generated-OAS diff; #14 ordered flow/errors/audit; harness execution OAS; UI control OAS. Design-system roles/organizations remain non-authoritative.

## Delivery and rollback forecast

Stacked-to-main first publishes S1 context, S2 proposal/core specs, S3 audit/conformance specs plus design, and S4 tasks. Dependency-adjusted contract/fixture slices then follow: A tooling; B shared schemas plus ADR-002/003/004; C audit/redaction plus ADR-005; D control plane/bootstrap; E Responses/OpenRouter plus ADR-001; F conformance/runtime-projection evidence. Each slice depends on its predecessor and splits before 400 lines. A merged dependent suffix rolls back only in reverse order `F→E→D→C→B→A`; C, D, or E cannot be reverted while later dependent slices remain. Planning slices likewise roll back `S4→S3→S2→S1` when reverting that chain. No runtime migration.

## Spec conflicts and risks

No normative contradiction found. Risks: OpenRouter extension drift, extra development Node runtime, external-ref variance, semantic-diff false positives/incompleteness, hard-limit discoverability, lifetime idempotency growth, spoofed correlation, pre-redaction sinks. Normalize/bundle before semantic comparison; validation fails on drift, unresolved refs, bad fixtures/examples, SemVer mismatch, or missing consumer evidence.
