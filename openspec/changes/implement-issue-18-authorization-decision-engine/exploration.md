## Exploration: Issue #18 — Reusable Principal–Action–Resource Decision Engine

### Current State

**Conclusion:** issue #18 is a feature request whose contract and first runtime path already exist, but whose reusable application boundary does not. The proposal should extract one authorization authority from the existing behavior rather than add a second policy model.

`Principal + grants` currently means:

- `Principal` is the sole subject identity, with `kind=human|agent` and `status=active|inactive`. Names, kinds, credentials, correlation IDs, and model aliases confer no role or permission.
- Authentication resolves an API key to `PrincipalContext`; authorization uses its `principal`, not the credential. HT-04 explicitly excludes grant lookup from authentication.
- `Grant` is one direct `allow` for an exact `(principal_id, action, resource_type, resource_id)` tuple. Only `active` grants participate; revoked, absent, wrong-action, wrong-resource, and wrong-principal records do not.
- `PolicyDecision` is already engine-independent and closed: allow is `allow/grant_matched/<grant_id>`; every deny is `deny/no_matching_grant/null`.
- PostgreSQL enforces allow-only grants and tuple uniqueness. `GrantRepository.find_active()` performs the exact lookup, while `GrantRepository.decide()` converts match/absence into `PolicyDecision`.
- `POST /v1/responses` adds missing policy precedence outside that repository: authentication must succeed; a missing/inactive logical resource or denied grant produces the same deny; routing and provider access occur only after allow.

The current implementation is safe for the Responses vertical because authentication rejects inactive Principals and the gateway separately checks resource status. However, `GrantRepository.decide()` alone is **not** a reusable authorization engine: called directly, it does not inspect Principal status or resource availability and can allow an exact grant for an inactive subject or inactive resource. It is also coupled to SQLAlchemy persistence. This is the minimal gap for #18.

The accepted contract already defines precedence without an external engine:

1. validation and authentication occur before authorization and are not policy decisions;
2. an inactive Principal denies;
3. a missing or inactive Resource denies, even if a grant row matches;
4. an exact active direct allow grant permits access;
5. every other case denies by absence, including revoked or mismatched grants.

All deny branches must preserve `reason_code=no_matching_grant` and `policy_id=null`; only an allow may expose the matching grant ID as `policy_id`. The HTTP layer may continue mapping missing and unauthorized resources to the non-enumerating `403 resource_unavailable`. Routing/provider data must remain unavailable until after allow.

Repository and GitHub evidence identifies the issue dependencies precisely:

- **HT-03 is GitHub #11**, `[HT-03] Implementar persistencia mínima de principals, recursos, grants y auditoría`. It is closed and supplied the schema, migrations, repositories, seeds, default-deny lookup, and direct-grant constraints.
- **HT-04 is GitHub #13**, `[HT-04] Autenticar principals mediante API key y resolver identidad interna`. It is closed and supplied reusable API-key-to-`PrincipalContext` authentication while explicitly excluding authorization.
- Issue #14 then composed both dependencies into the governed Responses path and proved authorize-before-routing and zero-call denial.
- Issue #17 added read-only threat-model and scenario catalogs. Those YAML files describe and test evidence; they are not runtime policy inputs.

`openspec/config.yaml` is stale: it still claims there is no backend, persistence, CI, or test runner and that strict TDD is disabled. Current FastAPI, PostgreSQL/Alembic, pytest, Compose, CI, migrations, and archived verification evidence contradict that text. Downstream phases must use live repository evidence and should reconcile the config separately; this exploration does not modify it.

### Affected Areas

- `src/sre_agent/governance/` — appropriate home for the reusable, framework- and persistence-independent authorization boundary using existing governance DTOs.
- `src/sre_agent/persistence/repositories.py` — retain exact active-grant/resource reads as persistence ports; avoid leaving `GrantRepository.decide()` as a competing decision authority.
- `src/sre_agent/gateway/responses.py` — replace inline resource-plus-grant composition with the reusable engine while preserving audit, 403 non-enumeration, and authorize-before-routing ordering.
- `src/sre_agent/governance/dto.py` and `schemas/releases/*` — existing `Principal`, `Resource`, `Grant`, and `PolicyDecision` semantics are authoritative; no contract expansion is currently justified.
- `tests/test_persistence_repositories.py` — preserve storage-query evidence but move full decision semantics to engine-focused tests.
- `tests/test_responses.py` — retain integration proof that missing/inactive/unauthorized resources are indistinguishable and never reach routing/upstream.
- `schemas/adrs/ADR-002-principal.md` and `schemas/adrs/ADR-004-grants.md` — accepted identity, default-deny, precedence, and `policy_id` authority.
- `docs/security/demo-grants.v1.yaml`, `docs/security/scenarios.v1.yaml`, and `docs/security/threat-model.md` — approved evidence/templates that must remain read-only and must not become a parallel policy store.
- `openspec/config.yaml` — stale project context requiring separate reconciliation before downstream planning relies on it.

### Approaches

1. **Extract one application authorization service over existing read ports** — accept an active-domain `Principal`, action, and resource identity; read authorization-safe resource state and the exact active grant; return the existing `PolicyDecision`.
   - Pros: closes the actual reuse gap; centralizes status/default-deny precedence; remains independent of FastAPI and SQLAlchemy; supports future LLM, MCP, skill, BoK, and control-plane callers without adding policy vocabulary.
   - Cons: requires replacing the gateway's inline composition and deciding a narrow port shape; repository tests and engine tests must be separated deliberately.
   - Effort: Medium

2. **Extract only a pure grant matcher** — pass a candidate `Grant | None` to a pure function that returns `PolicyDecision`, leaving Principal/resource eligibility with every caller.
   - Pros: smallest code movement and simplest unit tests.
   - Cons: does not centralize the precedence #18 asks to document; callers can repeat or omit inactive-subject/resource checks; leaves the unsafe reusable interpretation of `GrantRepository.decide()` unresolved.
   - Effort: Low

3. **Keep `GrantRepository.decide()` and add documentation/tests only** — treat the persistence method as the engine.
   - Pros: almost no production change; current Responses behavior remains intact.
   - Cons: SQLAlchemy-bound, incomplete outside the current gateway, and duplicates resource/principal precedence across future consumers; it does not satisfy reusable subject–action–resource semantics safely.
   - Effort: Low

External policy engines, roles/scopes, explicit deny records, condition languages, groups, tenancy, and YAML-driven runtime policy are rejected for this change because they conflict with accepted ADR-002/004 scope and create parallel authority.

### Recommendation

Use approach 1, but keep it deliberately narrow. Introduce one reusable application/domain authorization service with injected authorization-safe resource and grant lookup ports. Its public decision inputs should reuse the existing `Principal`, action string, and resource identity; `PrincipalContext` may be unwrapped by callers but credentials must never affect permission. Do not introduce a new public policy-input schema unless proposal/spec evidence proves a consumer needs one.

The engine should be the sole owner of the documented precedence above and the sole constructor path for runtime `PolicyDecision`. Persistence should answer facts (`resource state`, `matching active grant`), not decide policy. Migrate `ResponsesService` to this service and remove or narrow `GrantRepository.decide()` so two authorities cannot drift.

Minimum verification should cover human and agent Principals identically; inactive Principal; missing/inactive Resource; exact active allow; no grant; revoked grant; wrong principal/action/resource; `policy_id` consistency; no role inference from `admin-human`; no routing/provider access on deny; and unchanged 403/audit behavior through `/v1/responses`. The engine must never read model assignment, secrets, HTTP data, YAML catalogs, or provider state.

### Risks

- Treating #18 as greenfield policy work would duplicate contracts already owned by issues #9/#11 and ADR-004.
- Leaving Principal/resource eligibility outside the reusable boundary would make the current repository method unsafe for new consumers.
- Adding a new decision DTO, role/scope model, explicit deny, or policy store would create parallel authority and migration obligations without an approved requirement.
- Changing deny reasons for missing/inactive resources would break the closed `PolicyDecision` schema and non-enumeration contract.
- Querying routing assignment before allow would leak protected topology and regress issue #14.
- Using the issue #17 YAML catalogs at runtime would reverse their approved read-only evidence role.
- Stale `openspec/config.yaml` can misroute later design/testing decisions until reconciled with the live repository.

### Ready for Proposal

Yes. The orchestrator should tell the user that most policy semantics are already implemented and verified; #18 should be refined as extraction and hardening of one reusable authorization authority, not as a new IAM/policy subsystem. The proposal should freeze the precedence, ownership boundary, negative-case matrix, and removal/narrowing of the competing repository-level decision method. It should also flag the OpenSpec config reconciliation as a prerequisite housekeeping item, without expanding #18 into that unrelated edit.
