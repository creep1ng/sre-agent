-- Read-only: psql -v inc=<incident_id> -f query.sql. Nothing here writes.
BEGIN READ ONLY;
\echo '-- incident state, reserved postmortem id and incident version'
SELECT state->>'state' AS state, state->'postmortem'->>'postmortem_id' AS reserved_pm, version FROM incident.incidents WHERE incident_id = :'inc';
\echo '-- incident.postmortems (head row)'
SELECT postmortem_id, version, run_ids FROM incident.postmortems WHERE incident_id = :'inc';
\echo '-- incident.postmortem_revisions (append-only)'
SELECT r.version, r.edited_by, r.content->>'summary' AS summary, r.content->'cause'->>'certainty' AS certainty FROM incident.postmortem_revisions r JOIN incident.postmortems p USING (postmortem_id) WHERE p.incident_id = :'inc' ORDER BY r.version;
\echo '-- incident.postmortem_reviews (append-only)'
SELECT v.version, v.outcome, v.reviewer_id, v.comment FROM incident.postmortem_reviews v JOIN incident.postmortems p USING (postmortem_id) WHERE p.incident_id = :'inc' ORDER BY v.sequence;
\echo '-- close_incident approval, if any'
SELECT document->'approval'->>'postmortem_id' AS approved_pm, document->'approval'->>'postmortem_version' AS approved_version, document->'approval'->'actor_reference'->>'principal_id' AS approver FROM incident.decisions WHERE incident_id = :'inc' AND document->>'transition_id' = 'close_incident';
ROLLBACK;
