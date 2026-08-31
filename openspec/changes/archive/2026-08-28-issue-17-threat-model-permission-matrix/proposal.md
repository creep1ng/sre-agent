# Proposal: Define the MVP Threat Model and Security Evaluation Catalog

## Intent

Create a reviewable security baseline for the MVP. Grants, runtime behavior, and evidence are distributed across seeds, tests, specifications, and ADRs. This change publishes a threat model and machine-readable catalogs without claiming unimplemented protections.

## Scope

### In Scope
- Add `docs/security/threat-model.md` covering assets, trust boundaries, current/future threats, mitigations, residual risks, and exclusions.
- Add `docs/security/demo-grants.v1.yaml` for `admin-human`, `demo-human`, `incident-harness`, and `restricted-harness`; names confer no roles.
- Add `docs/security/scenarios.v1.yaml` with stable IDs, maturity, preconditions, HTTP/policy/audit expectations, execution counts, automation status, and evidence locators.
- Map current authentication and LLM allow/deny behavior to executable evidence, preserving `403 resource_unavailable` for missing and unauthorized resources.
- Describe redaction, MCP/tool, and administrative scenarios as future/specification-only where runtime support is absent.

### Out of Scope
- Runtime redactor, MCP/tool runtime, administrative control-plane runtime, new governance schema release, OAuth/OIDC, multi-tenancy, formal pentesting, and model-safety controls.

## Capabilities

### New Capabilities
- `mvp-security-evaluation`: Requirements for the versioned threat model, complete demo grant matrix, stable evaluation catalog, maturity labels, and evidence traceability.

### Modified Capabilities
- None.

## Approach

Use one concise Markdown entry point linked to ADR-004/005/006 and two versioned YAML catalogs. Treat seeds, specifications, and tests as evidence rather than duplicated policy. Validate current entries while keeping future entries explicitly non-executable.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `docs/security/threat-model.md` | New | Human-readable security baseline |
| `docs/security/demo-grants.v1.yaml` | New | Complete seeded permission matrix |
| `docs/security/scenarios.v1.yaml` | New | Stable evaluation scenario catalog |
| `tests/` | Modified | Catalog validation and evidence traceability |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Catalog drift | Medium | Validate seeds, behavior, and test locators |
| False assurance | Medium | Require maturity and automation labels |
| Policy contradiction | Low | Preserve default deny and non-enumerating 403 |
| Scanner noise | Low | Use unmistakably synthetic canaries |

## Rollback Plan

Revert the threat model, both YAML catalogs, and their validation tests together. Runtime authorization and auditing remain unchanged.

## Dependencies

- Issues #9 and #11 are complete on `main`; ADR-004/005/006 and existing main specifications remain authoritative.

## Success Criteria

- [ ] All four seeded principals, one resource, and the exact active grant are represented.
- [ ] Every current scenario has a passing test locator; every future scenario is marked non-executable.
- [ ] Missing and unauthorized resources both expect `403 resource_unavailable` and zero upstream calls.
- [ ] The threat model distinguishes metadata-only auditing today from unimplemented content redaction.
