# Governed incident Skill demo

These two original, instruction-only examples are for freelancers maintaining several
services. They illustrate the governed Skill lifecycle; they do not connect to or operate a
production system. `incident-triage@1.0.0` organizes supplied evidence. `postmortem-writer@1.0.0`
declares that exact triage version as a direct dependency and uses it only as evidence guidance.

## Reproduce

From the repository root, with Docker available and the repository's safe `.env.example` values:

```sh
docker compose --env-file .env.example --profile checks run --build --rm python-checks \
  sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_skill_demo.py'
```

The acceptance test resets its isolated PostgreSQL schema, publishes both JSON manifests through
the authenticated `/v1/skills/versions` producer, activates each exact version, and creates
separate `invoke` grants through `/v1/grants`. It then verifies that postmortem resolution is
unavailable until its direct triage dependency is granted, and that both exact versions resolve
as complete manifests once authority exists. It inspects persisted Skill, grant, and audit rows;
it does not call a model or external service. This is local controlled PostgreSQL evidence, not
live-service evidence.

## Acceptance evidence

| Criterion | Where to verify |
| --- | --- |
| **CA1 — persisted Skills** | The two versioned JSON manifests contain original instructions and exact dependency metadata. `tests/test_skill_demo.py` publishes them via the authenticated producer and reads both `skill_versions` rows; `tests/test_skill_publication.py` covers idempotent replay and immutable-version collision. |
| **CA2 — exact-version authorization** | `tests/test_skill_resolution.py` and this demo test resolve versioned URLs only with direct active invoke grants; unavailable resources use the same non-disclosing response. |
| **CA3 — atomic dependencies** | The postmortem URL returns unavailable without a separate direct grant for its triage dependency; after granting `incident-triage@1.0.0`, the response includes the complete root and dependency manifests. No transitive traversal is implied. |
| **CA4 — input validation** | `tests/test_skill_publication.py` exercises rejected Skill publications, including malformed and oversized manifests, through the authenticated producer. |
| **CA5 — lifecycle and revocation** | `tests/test_skill_lifecycle_proof.py` demonstrates pinned-version resolution across newer activation, status changes affecting the next request, and grant revocation through the authenticated HTTP route. |
| **CA6 — metadata-only audit** | The demo acceptance test correlates persisted `skills.resolve` events to requests and verifies neither Skill's instruction text appears in audit data. Resolution responses, not audit, carry authorized content. |

Rollback is limited to removing `demo/skills/`, this guide, and `tests/test_skill_demo.py`; no
runtime behavior or persisted production data is changed by these examples.
