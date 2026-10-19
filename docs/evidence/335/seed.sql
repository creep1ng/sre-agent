INSERT INTO incident.incidents (incident_id, state, version, created_at, updated_at) VALUES (
 'inc-pm335-demo',
 '{"workflow_id":"incident-response","workflow_version":"1.0.0","state":"verifying","incident_id":"inc-pm335-demo","linked_incident_id":null,"severity":"sev2","impact":"Checkout payments failing for part of the traffic.","alert":{"alert_id":"alt-pm335","service":"paymentservice","severity":"sev2","status":"triaged","observed_at":"2026-10-18T20:00:00Z","summary":"Elevated error rate on paymentservice.","source":"grafana-alerting"},"hypotheses":[],"evidence":[{"evidence_id":"ev_pm335","summary":"Error rate back to baseline after rollback."}],"mitigation_strategy":{"mitigation_id":"mit_pm335","approval_status":"approved","verification_check":"paymentservice error rate below 1% for 15 minutes"},"postmortem":null,"approvals":[],"updated_at":"2026-10-18T20:30:00Z"}',
 0, now(), now());
INSERT INTO incident.runs (run_id, incident_id, state, version, created_at, updated_at) VALUES (
 'run_pm335verify', 'inc-pm335-demo',
 '{"workflow_version":"1.0.0","current_state":"verifying","status":"running","pending_command":null}', 0, now(), now());
