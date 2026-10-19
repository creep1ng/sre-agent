\echo '-- incident.postmortems (head row)'
SELECT postmortem_id, incident_id, version, run_ids FROM incident.postmortems;
\echo '-- incident.postmortem_revisions (append-only)'
SELECT postmortem_id, version, edited_by, content->>'summary' AS summary, content->'cause'->>'certainty' AS certainty FROM incident.postmortem_revisions ORDER BY version;
\echo '-- incident.postmortem_reviews (append-only)'
SELECT postmortem_id, version, outcome, reviewer_id, comment FROM incident.postmortem_reviews ORDER BY sequence;
\echo '-- close decision approval and reserved id in the incident state'
SELECT d.document->'approval'->>'postmortem_id' AS approved_pm, d.document->'approval'->>'postmortem_version' AS approved_version, d.document->'approval'->'actor_reference'->>'principal_id' AS approver, i.state->>'state' AS state, i.state->'postmortem'->>'postmortem_id' AS reserved_pm FROM incident.decisions d JOIN incident.incidents i USING (incident_id) WHERE d.document->>'transition_id'='close_incident';
\echo '-- append-only guard'
UPDATE incident.postmortem_revisions SET edited_by='someone-else' WHERE version=1;
