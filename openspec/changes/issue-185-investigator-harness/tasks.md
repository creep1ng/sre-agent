# Tasks: Investigator Harness (Issue #185)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 1600-1800 total across the change |
| 400-line budget risk | High if delivered as one PR |
| Chained PRs recommended | Yes |
| Chain strategy | stacked-to-main |

The planning artifacts alone are about 250 lines, the contract with its tests about 380 and the loop with its tests about 370, so they travel as separate PRs. Artifacts are not compressed to fit.

### Work Units

| Unit | Goal | PR | Focused check |
|---|---|---|---|
| Planning | Proposal, design, tasks, capability delta | 1 | contract validators the design relies on |
| Contract | Request, actions, result, limits, correlation, import boundary | 2 | contract tests, `lint-imports`, mypy |
| Interpretation | Output parsing, reference validation, prompt assembly | 3 | parsing and prompt tests |
| Loop | Ports, bounded reducer, retries, step budget | 4 | loop tests against a scripted gateway |
| Client and provider | Gateway client from three variables, error mapping, labeled fixture evidence | 5 | client tests with an HTTP mock, provider tests |
| Demo | Deterministic server, scenarios, real call, guide | 6 | `docker compose` scenarios |

## Acceptance Mapping

| Criterion | Covered by | PR |
|---|---|---|
| CA1 validated result, no state writes | Contract, Loop | 2 and 4 |
| CA2 one re-interpretation, then human | Interpretation, Loop | 3 and 4 |
| CA3 unauthorized tool, unknown citation | Interpretation, Loop | 3 and 4 |
| CA4 step budget with observable reason | Loop | 4 |
| CA5 gateway denial is a block | Loop, Client | 4 and 5 |
| CA6 configuration only, no provider secret | Client, Demo | 5 and 6 |

Every criterion is demonstrated again end to end in PR 6.

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
- [x] 3.1 Output parsing, reference checks and prompt assembly
- [x] 4.1 Ports and bounded loop with re-interpretation, transient retry and step budget
- [x] 5.1 Gateway client and error mapping; fixture evidence provider
- [ ] 6.1 Demo server, scenarios, real call through the gateway and operator guide
