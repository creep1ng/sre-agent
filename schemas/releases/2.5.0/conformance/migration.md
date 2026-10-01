# 2.5.0 additive publication

Release 2.5.0 is additive over immutable 2.4.0. It publishes the already delivered administrator-only `GET /v1/usage/consumption` read route and its `usage.read` audit operation. It preserves prior schemas and consumers while declaring explicit request selectors, typed response fields, cost precision, evidence coverage, and bounded-read semantics.

The read aggregates only persisted `responses.create` evidence. It does not reserve funds, admit provider work, settle reservations, or enforce a limit. Those future reservation and settlement semantics remain coordinated with issue #334; this release does not create a second ledger or claim that issue's work is implemented.
