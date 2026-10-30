# Incident postmortem artifact (issue #335, first cut)

The workflow requires a postmortem before `close_incident`. This first cut stores a
human-written, versioned artifact in the `incident` schema and makes closure depend
on it. Generating a draft with the LLM is out of scope here (#335 CA1, #43 CA1).

## Where the artifact is created

`start_postmortem` (`resolved → postmortem`) reserves the identity: the runtime writes
`state.postmortem = {"postmortem_id": "pm_…"}` in the same transition, whichever
path executes it (`POST /v1/incidents/{id}/runs` with `objective: postmortem`, or a
future command). The content is written afterwards through its own route, under
that same id. The id in the state is a reservation, not proof: `close_incident`
reads the stored artifact and requires all of the following:

- an artifact exists with the reserved id and belongs to the same incident;
- its latest review approves its **current** version (an edit voids older reviews);
- the close approval records `postmortem_id` and `postmortem_version`.

The close takes a row lock on the artifact, so an edit that races the close waits.
Once it gets the lock, it either sees `closed` (and is refused) or lands first (and
the close is refused because the new version is unreviewed). A rejected close does
not change the incident.

## Storage

`incident.postmortems` holds one row per incident with the current version and the
incident's run ids. `incident.postmortem_revisions` (content per version) and
`incident.postmortem_reviews` are append-only, so the history of edits and reviews
is never overwritten. Migration `20261018_01`; readiness requires it.

## HTTP routes

| Route | Action | Notes |
| --- | --- | --- |
| `PUT /v1/incidents/{incident_id}/postmortem` | `run.command`, human | Body `{expected_version, content}`. `0` creates, `n` edits version `n`. 201/200 return the public projection. |
| `GET /v1/incidents/{incident_id}/postmortem` | `run.read` | Public projection. `content` and the review comment only with `run.read_context`. |
| `POST /v1/incidents/{incident_id}/postmortem/reviews` | `run.approve`, human | Body `{version, outcome: approved\|changes_requested, comment?}`. The reviewer is the authenticated principal. |

The public projection contains: `postmortem_id`, `incident_id`, `version`, `run_ids`,
`updated_by`, `created_at`, `updated_at`, `review {status, reviewed_version,
reviewer_id, reviewed_at}` and `content_included`. `review.status` is `pending`
unless the latest review is for the current version.

`content` requires exactly these sections (#43 CA2). Uncertainty is stated, never
omitted:

- `summary`, `impact`, `strategy`, `verification`: nonblank text.
- `cause`: `{statement, certainty}` with `certainty` in
  `confirmed | probable | hypothesis | unknown`.
- `timeline` (at least one) and `actions_taken`: `[{event_id, description}]`. Each
  `event_id` must be a stored event of this incident. An action is listed as
  performed only with the event that confirms it.
- `pending`, `unknowns`: lists of text.

Errors use the run error envelope:

- `401` and `403 not_authorized`.
- `404 incident_not_found` and `404 postmortem_not_found`.
- `409 postmortem_not_open`: the incident is not in `postmortem`.
- `409 postmortem_version_conflict`: a stale `expected_version` or review `version`, or a repeated create. Reload and retry by hand.
- `422 invalid_postmortem`: the minimum content is not met.
- `422 unknown_event_reference`.
- `503 storage_unavailable`.

## Incident memory (#773)

Closing an incident also indexes it as a memory, in the same transaction: if the memory
cannot be written, the close fails too. `incident.incident_memories` holds one append-only
row per closed incident. The row is the memory change log. It records what entered (the
alert, the postmortem cause, the mitigation that was approved, the strategy, the verification
and the summary), when it entered (`indexed_at`), and where it came from (the incident, the
approved postmortem version and the close event). Migration `20261030_01`.

When an investigation starts, the dispatcher looks up memories for the same service only.
It uses the BoK's PostgreSQL English full-text search (`websearch_to_tsquery`, `ts_rank_cd`;
see [BoK retrieval](bok-retrieval.md)) over any word of the alert's signal and summary, and
returns at most three. Each memory reaches the investigator as evidence with
`source: incident_memory`, and its `query` is the record it came from
(`/v1/incidents/{incident_id}/postmortem`). Recall only returns memories joined to their
approved postmortem revision. The investigator rejects a citation of any evidence id it was
not given, so it can only cite memories that have a source record. Memory is advisory: if
recall fails, the investigation continues without it.

| Route | Action | Notes |
| --- | --- | --- |
| `GET /v1/incident-memory/changes` | `run.read_context` | Change log, newest first, up to 100 entries: `memory_id`, `operation` (`added`), `incident_id`, `source_record`, `postmortem_id`, `postmortem_version`, `close_event_id`, `service`, `signal`, `indexed_at`, `content`. |
