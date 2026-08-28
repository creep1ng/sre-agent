## Exploration: Issue #17 — MVP threat model, permission matrix, and evaluation scenarios

### Current State

**Conclusion:** the change is ready for proposal. The repository already implements the core governed LLM allow/deny path; issue #17 needs to make that security posture explicit and traceable through a threat model, a versioned permission matrix, and stable evaluation scenarios.

Issue #9's accepted contracts and ADRs define a single-workspace model with `Principal.kind = human|agent`, direct active allow grants, default deny by absence, authorization before routing, non-enumerating execution errors, and fail-closed audit/redaction rules. Issue #11's persistence stack is present on `main` through integration commit `95a0a4f`, including deterministic seeds, repositories, and PostgreSQL-backed evidence.

The current runtime behaves as follows:

- `src/sre_agent/persistence/seeds.py` creates `admin-human`, `demo-human`, `incident-harness`, and `restricted-harness`, one `llm_model/triage-agent` resource, and exactly one active grant: `incident-harness × invoke × llm_model/triage-agent`.
- Principal names confer no roles. In particular, `admin-human` has no implicit administrative or LLM authority.
- `POST /v1/responses` authenticates before authorization, authorizes before routing, and calls the provider only after an exact active grant allows access.
- Missing/inactive resources and existing resources without a grant both return `403 resource_unavailable`; `tests/test_responses.py` proves they are indistinguishable and cause zero upstream calls. Issue #17's older 404 expectation must not override this non-enumeration guarantee.
- The runtime audit projector stores HMAC-protected metadata with `content_state=absent`. It does not persist prompt/response content and has no runtime redactor.
- ADR-005 specifies structural removal, known-secret matching, configured pattern detection, residual scanning, and fail-closed handling. ADR-006 permits bounded `sanitized_text` for successfully redacted LLM input/response, but explicitly defers runtime redactor implementation.
- Existing tests prove the directly automatable LLM allow and deny paths, revoked/invalid credential rejection, seed convergence, exact grant matching, secret-free persistence, append-only audits, and audit-failure suppression.

Threat maturity must remain explicit:

| Maturity | Threats |
| --- | --- |
| Current | Invalid, expired, or revoked credentials; direct-grant bypass; missing-resource enumeration; routing before authorization; audit leakage or mutation; release after audit persistence failure |
| Future/non-executable | Administrative control-plane authorization, audit-content read authorization, and MCP/tool authorization |

The current Responses request is closed and text-only, so unsupported tool fields fail validation with 422. A future unauthorized MCP scenario may be specified now, but the later MCP-capable runtime must own its 403 deny and zero-execution proof. Likewise, administrative scenarios must use explicit action/resource grants rather than infer authority from the `admin-human` name.

The checked-in `openspec/config.yaml` context is stale: it still says the repository has no backend, persistence, containers, CI, or test runner. Current source, main specs, tests, and Git history prove those capabilities now exist. Downstream planning must use current repository evidence and avoid repeating that obsolete snapshot.

### Affected Areas

- `docs/security/threat-model.md` — new human-facing security posture, assets, trust boundaries, current/future threats, mitigations, residual risks, and exclusions.
- `docs/security/demo-grants.v1.yaml` — new versioned Principal × action × resource matrix derived from the deterministic seed graph.
- `docs/security/scenarios.v1.yaml` — new machine-readable scenario catalog with stable IDs and explicit HTTP, policy decision, upstream/tool execution, audit, maturity, and automation fields.
- `schemas/adrs/ADR-004-grants.md` — existing authority for direct allow, default deny, and authorization-before-routing; link rather than duplicate it.
- `schemas/adrs/ADR-005-audit-redaction.md` and `schemas/adrs/ADR-006-sanitized-audit-content.md` — existing official redaction policy and runtime-maturity boundary.
- `src/sre_agent/persistence/seeds.py` — current source for demo principals, the triage resource, and the active grant.
- `src/sre_agent/gateway/responses.py` and `src/sre_agent/gateway/audit.py` — current HTTP, authorization, upstream, and metadata-only audit behavior.
- `tests/test_responses.py` — current allow, deny, hidden-resource, and audit-release-gate evidence; suitable for stable scenario mappings.
- `tests/test_authentication.py`, `tests/test_api_key_persistence.py`, `tests/test_demo_seeds.py`, and `tests/test_persistence_repositories.py` — current credential, seed, direct-grant, and audit evidence.
- `openspec/config.yaml` — stale project context discovered during exploration; not modified in this phase.
- `openspec/changes/issue-127-bounded-tool-calling/` — unrelated future tool-calling work; it must remain untouched.

### Approaches

1. **Threat model plus versioned YAML catalogs** — create one concise Markdown threat model and separate machine-readable matrix and scenario catalogs; map current scenario IDs to executable pytest evidence.
   - Pros: stable identifiers, reviewable diffs, direct automation path, clear current/future maturity, and alignment with the repository's YAML-based conformance patterns.
   - Cons: requires structural validation to prevent documentation and runtime drift.
   - Effort: Medium

2. **Single Markdown document** — keep the threat model, permission matrix, and scenario tables together.
   - Pros: lowest authoring cost and simple human review.
   - Cons: weak machine consumption, unstable test references, and greater drift risk.
   - Effort: Low

3. **New governance contract release** — add JSON Schemas and release fixtures for the matrix and scenario catalog under `schemas/releases/`.
   - Pros: strongest formal validation and immutable contract identity.
   - Cons: expands a QA/security documentation change into contract-version governance and duplicates existing Principal/Grant/PolicyDecision contracts.
   - Effort: High

### Recommendation

Use approach 1. Make `docs/security/threat-model.md` the review entry point and keep the versioned YAML artifacts small enough to load directly in tests.

The effective demo matrix should include every seeded Principal, not only the three listed in issue #17:

| Principal | Action | Resource | Effective result |
| --- | --- | --- | --- |
| `incident-harness` | `invoke` | `llm_model/triage-agent` | Allow through the active seeded grant |
| `restricted-harness` | `invoke` | `llm_model/triage-agent` | Deny by absence |
| `admin-human` | `invoke` | `llm_model/triage-agent` | Deny by absence |
| `demo-human` | `invoke` | `llm_model/triage-agent` | Deny by absence |

Start the scenario catalog with stable entries equivalent to:

| ID | Maturity | Expected outcome |
| --- | --- | --- |
| `SEC-LLM-ALLOW-001` | Current/automatable | Valid incident key; HTTP 200; allow; one upstream call; durable success audit |
| `SEC-LLM-DENY-001` | Current/automatable | Restricted principal; HTTP 403; deny; zero upstream calls; durable deny audit |
| `SEC-AUTH-REVOKED-001` | Current | Revoked key; HTTP 401; policy not evaluated; zero upstream calls; no secret persistence |
| `SEC-AUTH-INVALID-001` | Current | Invalid key; HTTP 401; policy not evaluated; zero upstream calls; safe audit evidence |
| `SEC-RESOURCE-HIDDEN-001` | Current/automatable | Missing alias; HTTP 403 `resource_unavailable`; deny; zero upstream calls; no routing evidence |
| `SEC-REDACTION-001` | Contracted/future runtime | Synthetic known-secret canary is removed before persistence or content fails closed; no raw/partial fallback |
| `SEC-MCP-DENY-001` | Future | Unauthorized MCP/tool action denies before execution and records safe audit evidence |
| `SEC-ADMIN-DENY-001` | Future | Administrative action without an exact capability grant denies without role inference |

Each catalog entry should carry at least: stable ID, maturity, threat, preconditions, credential state, Principal, action, resource, request shape, expected HTTP status/code, policy decision or `not_evaluated`, upstream/tool call count, audit expectation, automation status, and test locator.

Document the redaction process in policy order: structural sensitive-field removal → known-secret replacement → configured-pattern replacement → residual scan → closed safe-representation construction → schema validation → durable audit append before result release. Error or uncertainty must discard content, set `redaction_failed`, retain only safe category/count metadata, and never fall back to raw or partially redacted content.

Use an unmistakably synthetic registered canary instead of a provider-shaped credential. Repository history already contains scanner-noise remediation around credential-like test values; the scenario should prove redaction without introducing another false positive.

The likely authored change may exceed the ordinary 400-line review budget once documentation, YAML validation, and test traceability are combined. With the confirmed `auto-chain` and `stacked-to-main` strategy, planning should separate reviewable documentation/catalog and automation slices if the forecast crosses that limit.

### Risks

- Retaining issue #17's stale 404 would violate accepted and implemented non-enumeration behavior.
- Schema fixtures can be mistaken for proof that a runtime redactor exists.
- Omitting seeded `demo-human` would make the demo permission matrix incomplete.
- Treating `admin-human` as a role would violate the Principal and direct-grant contracts.
- YAML artifacts can drift from seeds and runtime unless tests validate them structurally and behaviorally.
- MCP, control-plane administration, and content retrieval can be overstated unless labeled future/non-executable.
- Credential-shaped synthetic values can trigger secret-scanner findings.
- The stale OpenSpec config context can mislead later phases if it is treated as current architecture evidence.
- Runtime redactor implementation, MCP execution, OAuth/OIDC, tenancy, formal pentesting, and model-safety controls are scope expansion.

### Ready for Proposal

Yes. The proposal should freeze the Markdown-plus-versioned-YAML approach, preserve non-enumerating 403 behavior, include `demo-human`, make Principal names non-authoritative, distinguish metadata-only audit runtime from the contracted redactor, and keep MCP/admin scenarios future-only. No proposal, code, or unrelated change was created during this phase.
