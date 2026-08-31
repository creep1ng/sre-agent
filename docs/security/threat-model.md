# MVP Security Threat Model

## Purpose and evidence

This document is a review entry point for the versioned evaluation catalogs. It describes
current runtime evidence and contracted or future controls; it does not grant permissions or
claim that deferred runtimes exist.

## Catalog links

- [Demo grant matrix](demo-grants.v1.yaml)
- [Security scenario catalog](scenarios.v1.yaml)

Authoritative decisions: [ADR-004](../../schemas/adrs/ADR-004-grants.md),
[ADR-005](../../schemas/adrs/ADR-005-audit-redaction.md), and
[ADR-006](../../schemas/adrs/ADR-006-sanitized-audit-content.md).

## Assets

- API-key credentials, principal identities, direct grants, and the `triage-agent` resource.
- Response requests, provider outputs, and audit-event metadata.
- The non-enumerating authorization result: `403 resource_unavailable`.

## Trust boundaries

- Callers present credentials; authentication resolves a principal before authorization.
- Authorization uses only an active, exact direct grant before model routing or provider calls.
- The gateway writes accepted audit metadata before releasing an outcome; providers do not decide
  grants and the YAML catalogs are read-only evidence.

## Current controls

| Concern | Maturity | Evidence and mitigation |
|---|---|---|
| Authentication and exact grants | Current | ADR-004; grant absence is default deny and names confer no role. |
| Resource hiding | Current | Missing and unauthorized resources both return `403 resource_unavailable` before routing. |
| Audit durability | Current | Metadata-only audit is append-only and failure suppresses result release. |
| Catalog integrity | Current | `tests/test_security_catalogs.py` validates seeded identities and catalog structure. |

## Runtime evidence locators

Current executable catalog entries reference
`tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback`
and `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`.
They are evidence for current behavior, not evidence that future redaction, MCP, or administrative
runtimes exist.

## Future and contracted controls

| Concern | Maturity | Required evidence |
|---|---|---|
| Sanitized audit content | Contracted future | ADR-006 contract; a runtime redactor must prove safe handling before use. |
| Runtime redaction | Future/non-executable | No runtime redactor is implemented; do not claim content protection beyond current metadata-only audit. |
| MCP/tool authorization | Future/non-executable | Exact tool grants, pre-execution denial, and safe audit evidence. |
| Administrative controls | Future/non-executable | Exact control-plane grants, pre-execution denial, and safe audit evidence. |

## Residual risks

- Current audit events intentionally omit raw prompt and response content; this limits forensic
  detail until a proven redaction implementation exists.
- Future MCP and administrative runtimes have no executable authorization evidence yet.
- Catalogs can drift from behavior; structural tests and cataloged runtime locators expose drift.

## Exclusions

This baseline excludes OAuth/OIDC, multi-tenancy, policy engines, formal penetration testing,
model-safety controls, a runtime redactor, MCP/tool runtime, and an administrative control-plane
runtime. These exclusions do not weaken the current direct-grant and non-enumeration contract.
