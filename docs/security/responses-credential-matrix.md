# Responses credential-boundary matrix

The PostgreSQL CI job runs this twelve-cell public-boundary matrix verbosely before the
remaining database-backed tests. It proves that a Responses request is either authenticated,
authorized, routed once, and audited, or it stops before the next authority boundary.

## Evidence mapping

| Credential | Attempted principal | Alias | Public status | Upstream calls | Correlated metadata-only audit |
|---|---|---|---:|---:|---|
| valid | authorized | existing | 200 | 1 | response / 200 |
| valid | authorized | missing | 403 | 0 | authorization / 403 |
| valid | unauthorized | existing | 403 | 0 | authorization / 403 |
| valid | unauthorized | missing | 403 | 0 | authorization / 403 |
| invalid | authorized | existing | 401 | 0 | authentication / 401 |
| invalid | authorized | missing | 401 | 0 | authentication / 401 |
| invalid | unauthorized | existing | 401 | 0 | authentication / 401 |
| invalid | unauthorized | missing | 401 | 0 | authentication / 401 |
| revoked | authorized | existing | 401 | 0 | authentication / 401 |
| revoked | authorized | missing | 401 | 0 | authentication / 401 |
| revoked | unauthorized | existing | 401 | 0 | authentication / 401 |
| revoked | unauthorized | missing | 401 | 0 | authentication / 401 |

An invalid credential has no resolved Principal. The principal values in those rows identify
the attempted credential family for coverage only; they are not identity evidence.

## Reproduce locally

Use an isolated disposable PostgreSQL database. The module fixture drops and recreates the governance
and audit tables before seeding, so **never** point this command at a shared or production database.

```bash
TEST_DATABASE_URL=postgresql://sre_agent@127.0.0.1:5432/sre_agent \
  pytest -vv tests/test_responses.py::test_public_responses_credential_matrix
```

## Test boundary

`tests/test_responses.py::test_public_responses_credential_matrix` records each provider request
and wraps resource, grant, and assignment reads. Invalid and revoked credentials therefore prove
zero authorization and routing reads; denied valid requests prove zero provider calls. Every row
requires exactly one audit event selected by its public `request_id`, with absent content and no
credential, input, or provider output in audit data or captured logs. Public responses and captured
logs exclude internal authorization causes; governed audit data retains the winning denial cause for
403 evidence. Public denials remain non-enumerating `resource_unavailable`; a successful response
may return its provider output by design.

The matrix extends, rather than replaces, the issue #18 authorization evidence:

- `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`
- `tests/test_responses.py::test_inactive_principal_reaches_the_engine_before_all_authorization_reads`
- `tests/test_responses.py::test_inactive_resource_stops_before_grant_and_routing_reads`
- `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback`
