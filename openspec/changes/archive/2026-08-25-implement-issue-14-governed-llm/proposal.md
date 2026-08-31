# Proposal: Governed LLM Responses Vertical Slice

## Intent

Deliver governed `POST /v1/responses` for `triage-agent`: allowed principals receive normalized results; restricted principals receive 403 without upstream traffic. Every attempt leaves durable metadata-only evidence.

## Scope

### In Scope
- Implement the HT-01 text-only, non-streaming subset with normalized success/errors.
- Authenticate API keys; read authorization-safe logical state; decide the direct `invoke` grant; resolve routing only after allow.
- Add an application-owned direct async HTTP OpenRouter port/adapter for one provider/model, without retries or fallback.
- Validate bounded selected-provider evidence and reject invalid evidence safely.
- Commit HMAC-projected audit metadata, including `latency_ms`, before releasing any outcome.
- Add PostgreSQL recording-adapter tests and a separate secret-gated one-request live smoke.

### Out of Scope
- Streaming; a second provider; fallback or advanced retry; consumption limits/budgets.
- Tool calling/MCP; skills or BoK; persistent conversations.
- Persisting or logging prompts, model output, or provider bodies.

## Capabilities

### New Capabilities
- `governed-llm-responses`: HT-01 execution, authorize-before-routing, normalization, and no-upstream denial.
- `runtime-audit-evidence`: Durable attempt metadata, latency, and release gating.

### Modified Capabilities
None; `openspec/specs/` does not yet exist.

## Approach

Assign one `request_id`; authenticate; read logical identity/status; authorize; audit and return uniform 403 on deny. After allow, resolve alias/model/provider, call OpenRouter once outside database transactions, validate evidence/text, normalize to HT-01, commit terminal audit, then release. Publish an immutable additive contract release: `latency_ms` is backward-compatible, mandatory here, and non-null in persistence.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `schemas/`, migrations, governance | Modified | Add latency evidence. |
| gateway, persistence, composition | New/Modified | Governed flow and adapter. |
| Tests, Compose/CI/docs | Modified | Deterministic and live proof. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Premature routing leak | Medium | Separate projections; assert zero deny calls. |
| Provider evidence drift | Medium | Closed projection; invalid maps to 502. |
| Ambiguous failure durability | Medium | Short transactions; audit gates release. |

## Rollback Plan

Remove route/adapter wiring and migration; revert the additive release while retaining prior contracts and audits.

## Dependencies

- Issues #9, #11, #13; OpenRouter; API-only provider and audit secrets.

## Success Criteria

- [ ] `incident-harness` receives parseable 200 via the alias without provider credentials.
- [ ] `restricted-harness` receives 403, zero upstream calls, and committed deny audit.
- [ ] Attempts record principal, resource, decision, status, applicable routing, and `latency_ms`.
- [ ] Provider failures normalize per HT-01; deterministic and live-smoke tests pass.
