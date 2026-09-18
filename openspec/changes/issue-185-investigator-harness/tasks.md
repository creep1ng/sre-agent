# Tasks: Investigator Harness (Issue #185)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 1500-1700 total across the change |
| 400-line budget risk | High if delivered as one PR |
| Chained PRs recommended | Yes |
| Chain strategy | stacked-to-main |

The planning artifacts alone are about 250 lines and the contract with its tests about 380, so they travel as separate PRs. Artifacts are not compressed to fit.

### Work Units

| Unit | Goal | PR | Focused check |
|---|---|---|---|
| Planning | Proposal, design, tasks, capability delta | 1 | contract validators the design relies on |
| Contract | Request, actions, result, limits, correlation, import boundary | 2 | contract tests, `lint-imports`, mypy |
| Loop | Output parsing, reference validation, bounded reducer, retries | 3 | parsing and loop tests against a scripted gateway |
| Client and provider | Gateway client from three variables, error mapping, labeled fixture evidence | 4 | client tests with an HTTP mock, provider tests |
| Demo | Deterministic server, scenarios, real call, guide | 5 | `docker compose` scenarios |

## Acceptance Mapping

| Criterion | Covered by | PR |
|---|---|---|
| CA1 validated result, no state writes | Contract, Loop | 2 and 3 |
| CA2 one re-interpretation, then human | Contract, Loop | 2 and 3 |
| CA3 unauthorized tool, unknown citation | Contract, Loop | 2 and 3 |
| CA4 step budget with observable reason | Loop | 3 |
| CA5 gateway denial is a block | Client | 4 |
| CA6 configuration only, no provider secret | Client, Demo | 4 and 5 |

Every criterion is demonstrated again end to end in PR 5.

## Definition of Ready

| Item | Status |
|---|---|
| Context received and results accepted | Met: `design.md`, aligned with run-state and run-context |
| Gateway API and a demo alias | Met in `main`; a real call needs a provider key in the gateway's `.env` |
| Test incident, allowed and restricted credential | Met: `agent/fixtures/incidents/otel-payment-failure/declared-state.yaml`, seeded `incident-harness` and `restricted-harness` |
| Step limit and timeouts | Met: set in `design.md` by the issue assignee |

## Tasks

- [x] 1.1 Proposal, design, tasks and capability delta
- [x] 2.1 `contract.py`: request, actions, result, limits and `task_id` derivation
- [x] 2.2 Import contract and strict mypy scope for the package
- [x] 2.3 Contract tests, including run-context and incident-state conformance
- [ ] 3.1 Output parsing and reference checks
- [ ] 3.2 Bounded loop with re-interpretation and step budget
- [ ] 4.1 Gateway client and error mapping; fixture evidence provider
- [ ] 5.1 Demo server, scenarios, real call through the gateway and operator guide
