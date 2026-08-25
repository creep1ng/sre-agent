# Design: Governed LLM Responses Vertical Slice

## Technical Approach

`POST /v1/responses` orchestrates request ID, validation, authentication, safe lookup, grant, then routing. An async port isolates OpenRouter HTTP. Ordinary outcomes require durable metadata-only terminal-event acceptance; rejection becomes 503.

## Architecture Decisions

| Decision | Choice / tradeoff |
|---|---|
| Provider | `LLMProvider.create(ProviderRequest) -> ProviderResult`; shared pinned `httpx.AsyncClient`, no retry/fallback, exposes transport behavior. SDK authority rejected. |
| Ordering | `responses_router(service)` owns validation through audit; independent FastAPI dependencies cannot guarantee ordering/auditing. |
| Safe reads | `authorization_view()` selects type/ID/status; post-allow `resolve_assignment()` selects routing. ORM-row projection is still premature access. |
| Audit | `AuditProjector` emits ADR-005 HMACs and `content_state=absent`; raw identifiers/provider objects are rejected. |
| Latency | Full immutable `1.2.0`; optional-additive schema/DTO, issue-14-required, PostgreSQL non-null. Rewriting 1.1.0 or DB-only evidence is rejected. |

## Request and Transaction Sequence

```text
request -> validate -> authenticate -> TX1[logical resource + grant] -> close
 deny -> TX2[audit 403] -> commit -> 403
 allow -> TX2[assignment] -> close -> provider once -> normalize
       -> TX3[terminal audit] -> commit -> release
 audit rejection ----------------------------------------------> 503
```

The monotonic timer covers entry through terminal decision/normalization. No SQL session spans provider I/O.

## HTTP-to-Audit Contract

Public codes are not audit reason codes; the producer maps them:

| HTTP / public code | Audit stage / closed `reason_code` / retryable | Subject evidence under immutable 1.1.0 semantics |
|---|---|---|
| 422 `contract_validation_failed` | validation / `contract_validation_failed` / false | Identity, resource, alias, decision, routing forbidden. |
| 401 `authentication_failed` | authentication / `authentication_failed` / false | Identity absent, or permitted safe partial/credential-only HMAC; other subject fields forbidden. |
| 403 `resource_unavailable` | authorization / `no_matching_grant` / false | Authenticated identity, HMACs of requested logical resource/alias, deny decision; routing absent. These references do not assert existence. |
| 200 completed | response / null / false | Identity, resource, alias, allow decision, routing required. |
| 502 `provider_evidence_invalid` or `upstream_invalid_response` | upstream / `upstream_invalid` / false | Full allowed subject and routing required. |
| 503 `upstream_unavailable` | upstream / `upstream_unavailable` / true | Full allowed subject and routing required. |
| 504 `upstream_timeout` | upstream / `upstream_failed` / true | Full allowed subject and routing required. |
| 503 `audit_unavailable` | audit / `audit_unavailable` / true | Subject fields forbidden; rejection suppresses the intended outcome and never claims persistence. |

Early attempts remain stage-aware. Release 1.2.0 adds only latency; relationships stay unchanged.

## Provider Contract

`ProviderRequest` carries input, model, provider. The adapter sends non-streaming `/api/v1/responses`, metadata enabled, one-provider allow-list, `allow_fallbacks=false`. `ProviderResult` admits bounded ID/model/text and exactly one matching provider. Invalid, extra, oversized, or unadaptable evidence becomes 502; only bounded validated `Retry-After` passes.

## File Changes

| Paths | Action / purpose |
|---|---|
| `src/sre_agent/gateway/{responses,providers,openrouter,audit}.py` | Create orchestration, port/adapter, normalization, errors, HMAC audit. |
| `src/sre_agent/{application,settings}.py` | Inject/configure provider, secrets, timeouts; close client. |
| `src/sre_agent/governance/dto.py`, `src/sre_agent/persistence/{models,repositories,projections}.py` | Add latency and separated projections. |
| `schemas/releases/1.2.0/**` | Self-contained immutable snapshot: all 21 versioned JSON Schemas with `1.2.0` IDs/references; both OpenAPI documents; examples, fixtures, ADR, conformance/evidence, and manifest inventories. Only `latency_ms` is semantically additive; the remainder is packaging. |
| `schemas/tooling/release.mjs`, `schemas/tooling/lib/release-validation.mjs`, `schemas/tooling/lib/governance-validation.mjs`, `schemas/tooling/test/release-validation.test.mjs`, `schemas/tooling/test/governance-validation.test.mjs` | Admit, validate, and test 1.2.0 baseline/ADR ownership. |
| `migrations/versions/20260825_02_add_audit_latency.py`, `tests/test_migrations.py`, `tests/test_governance_dto.py`, `tests/test_persistence_projections.py`, `tests/test_persistence_repositories.py` | Migrate/backfill and prove contracts/readback. |
| `pyproject.toml`, `uv.lock` | Promote pinned `httpx==0.28.1` from dev-only to runtime and refresh the lock; the runtime image installs main dependencies only. |
| `tests/test_responses.py`, `tests/test_openrouter_live.py`, `compose.yaml`, `.env.example`, `.github/workflows/ci.yml`, `README.md`, `docs/architecture.md` | Runtime proof, API-only secrets, commands/docs. |

## Testing Strategy

RED PostgreSQL tests prove ordering, call counts, mappings, protected readback, latency, transaction closure, and audit suppression. `httpx.MockTransport` proves request/evidence bounds/redaction. The live test skips without enablement/secrets, makes one request, and CI excludes it.

## Threat Matrix

| Boundary | Cases | Applicability | Safe/failure behavior | Planned RED tests |
|---|---|---|---|---|
| LLM routing | pre-allow; client injection; invalid/extra evidence | Applicable | Route once after allow; reject injection/evidence; no fallback | deny count; injection 422; evidence 502 |
| Documentation-like paths | executable docs/build files | N/A: no classification/execution | No execution boundary | None |
| Git repository selection | relative/absolute `git -C` | N/A: no Git process | No selector | None |
| Commit state | staged/`commit -a`/empty index | N/A: no commit automation | No index mutation | None |
| Push state | tracking/first push/refspec | N/A: no push automation | No remote mutation | None |
| PR commands | `--head`/environment/composition | N/A: no PR automation | No command composition | None |

## Migration / Rollout

Publish 1.2.0, migrate existing rows to `latency_ms=0`, retain `NOT NULL CHECK (latency_ms >= 0)` without a server default, then deploy runtime. After durable use, roll back runtime without deleting the additive release/column.

## Open Questions

None.
