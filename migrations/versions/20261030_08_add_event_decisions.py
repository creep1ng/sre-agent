"""Decide, for every incoming event, whether to ignore, remember, digest or interrupt (#771).

Silence is the default. Every alert episode, resolution, change event and investigation result
gets exactly one row in `incident.event_decisions`, written by a trigger in the transaction that
records the event, so no code path can skip the policy. The policy decides when to ask a person,
never what is allowed:
- an investigation interrupts only while its alert still fires (sustained impact) and a human
  decision is pending (a proposed mitigation, a request for a person, or no conclusion);
- an alert that recovered before its investigation ended goes to the daily digest;
- the same rule firing again on the same service within an hour is ignored as a repeat;
- a run a person started is answered in the chat, as before: they asked for it.
Only an interrupt queues an immediate chat message; the acknowledgment is sent only to a person
who started the run. A pending mitigation's message is #767's decision message when that
revision is present, so the operator gets one message, not a conclusion and then a decision;
that message is sent only when this policy interrupts (integration 2026-11-01).
"""

from alembic import op

revision = "20261030_08"
down_revision = "20261030_07"
branch_labels = None
depends_on = None

_ENQUEUE_766 = """
      DECLARE
        phase text := NEW.payload -> 'dispatch_receipt' ->> 'phase';
        kind text := CASE phase WHEN 'intent' THEN 'investigation_ack'
                                WHEN 'outcome' THEN 'investigation_conclusion' END;
      BEGIN
        IF kind IS NOT NULL THEN
          INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
          SELECT chat_id, kind, kind || ':' || NEW.run_id,
                 jsonb_build_object('incident_id', NEW.incident_id, 'run_id', NEW.run_id,
                                    'event_id', NEW.event_id)
          FROM incident.chat_links
          ON CONFLICT (chat_id, dedup_key) DO NOTHING;
        END IF;
        RETURN NULL;
      END"""


# #767's decision message (revision 20261030_07); `{gate}` is where the policy's condition goes.
_ENQUEUE_DECISION_767 = """
      DECLARE
        mitigation text := NEW.payload -> 'incident_state' -> 'mitigation_strategy'
                           ->> 'mitigation_id';
      BEGIN{gate}
        INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
        SELECT chat_id, 'mitigation_decision',
               'mitigation_decision:' || NEW.run_id || ':' || mitigation,
               jsonb_build_object('incident_id', NEW.incident_id, 'run_id', NEW.run_id,
                 'mitigation_id', mitigation, 'proposed_at', NEW.occurred_at,
                 'link', code_sha256, 'principal_id', principal_id,
                 'token', replace(gen_random_uuid()::text, '-', ''),
                 'incident_version', (SELECT version FROM incident.incidents
                                      WHERE incident_id = NEW.incident_id))
        FROM incident.chat_links
        ON CONFLICT (chat_id, dedup_key) DO NOTHING;
        RETURN NULL;
      END"""
# The decision trigger is deferred, so it sees the run's decision written by the outcome receipt
# of the same transaction: a spike that recovered before its proposal (digest) asks nobody.
_INTERRUPT_GATE = """
        IF NOT EXISTS (SELECT 1 FROM incident.event_decisions
                       WHERE event_kind = 'investigation' AND event_id = NEW.run_id
                         AND decision = 'interrupt') THEN
          RETURN NULL;
        END IF;"""


def upgrade() -> None:
    # One decision per event: (event_kind, event_id) is the episode, change or run it decides.
    op.execute("""CREATE TABLE incident.event_decisions (
      decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      event_kind varchar(16) NOT NULL,
      event_id varchar(200) NOT NULL,
      service varchar(200),
      incident_id varchar(64),
      title text NOT NULL,
      occurred_at timestamptz NOT NULL,
      decision varchar(16) NOT NULL,
      rule varchar(64) NOT NULL,
      reason text NOT NULL,
      decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      CONSTRAINT uq_event_decision UNIQUE (event_kind, event_id),
      CONSTRAINT ck_event_decision_kind
        CHECK (event_kind IN ('alert', 'resolution', 'change', 'investigation')),
      CONSTRAINT ck_event_decision
        CHECK (decision IN ('ignore', 'remember', 'digest', 'interrupt'))
    )""")
    op.execute(
        "CREATE INDEX ix_event_decisions_decided ON incident.event_decisions (decided_at DESC)"
    )
    op.execute("""CREATE TRIGGER event_decisions_append_only BEFORE UPDATE OR DELETE
      ON incident.event_decisions FOR EACH ROW
      EXECUTE FUNCTION incident.reject_append_only_mutation()""")

    # How long an alert fired, as the reasons say it.
    op.execute("""CREATE FUNCTION incident.lasted(span interval) RETURNS text
      LANGUAGE sql IMMUTABLE AS $$
        SELECT CASE WHEN span < interval '1 minute' THEN 'en menos de un minuto'
                    ELSE 'en ' || ceil(extract(epoch FROM span) / 60) || ' min' END
      $$""")
    op.execute("""CREATE FUNCTION incident.decide_alert_episode() RETURNS trigger
      LANGUAGE plpgsql AS $$
      DECLARE
        title text := NEW.rule || ' en ' || NEW.service;
        repeat_of text;
        lasted text;
      BEGIN
        IF TG_OP = 'INSERT' AND NEW.status = 'firing' THEN
          SELECT episode_id INTO repeat_of FROM incident.alert_episodes
          WHERE service = NEW.service AND rule = NEW.rule AND episode_id <> NEW.episode_id
            AND last_received_at > NEW.first_received_at - interval '1 hour'
          ORDER BY first_received_at DESC LIMIT 1;
          INSERT INTO incident.event_decisions
            (event_kind, event_id, service, title, occurred_at, decision, rule, reason)
          VALUES ('alert', NEW.episode_id, NEW.service, title, NEW.starts_at,
            CASE WHEN repeat_of IS NULL THEN 'remember' ELSE 'ignore' END,
            CASE WHEN repeat_of IS NULL THEN 'investigating' ELSE 'repeat' END,
            CASE WHEN repeat_of IS NULL
              THEN 'Se investiga sin avisarte; el resultado decide si te escribo.'
              ELSE 'La misma alerta se repitió en la última hora; se agrupa con ' || repeat_of
                   || '.' END)
          ON CONFLICT ON CONSTRAINT uq_event_decision DO NOTHING;
        ELSIF NEW.status = 'resolved' AND (TG_OP = 'INSERT' OR OLD.status = 'firing') THEN
          lasted := incident.lasted(COALESCE(NEW.resolved_at, clock_timestamp()) - NEW.starts_at);
          INSERT INTO incident.event_decisions (event_kind, event_id, service, incident_id,
            title, occurred_at, decision, rule, reason)
          VALUES ('resolution', NEW.episode_id, NEW.service, NEW.incident_id, title,
            COALESCE(NEW.resolved_at, clock_timestamp()),
            CASE WHEN TG_OP = 'INSERT' THEN 'ignore' ELSE 'remember' END,
            CASE WHEN TG_OP = 'INSERT' THEN 'resolved_unseen' ELSE 'recovered' END,
            CASE WHEN TG_OP = 'INSERT'
              THEN 'Llegó resuelta sin un disparo previo: no hubo impacto que contar.'
              ELSE 'Se recuperó ' || lasted || '; la investigación decide si va al resumen.'
              END)
          ON CONFLICT ON CONSTRAINT uq_event_decision DO NOTHING;
        END IF;
        RETURN NULL;
      END $$""")
    op.execute("""CREATE TRIGGER alert_episodes_decision
      AFTER INSERT OR UPDATE OF status ON incident.alert_episodes
      FOR EACH ROW EXECUTE FUNCTION incident.decide_alert_episode()""")

    op.execute("""CREATE FUNCTION incident.decide_change_event() RETURNS trigger
      LANGUAGE plpgsql AS $$
      BEGIN
        INSERT INTO incident.event_decisions
          (event_kind, event_id, service, title, occurred_at, decision, rule, reason)
        VALUES ('change', NEW.change_id, NEW.service,
          CASE NEW.kind WHEN 'deploy' THEN 'Despliegue' WHEN 'rollback' THEN 'Rollback'
                        ELSE 'CI' END
            || COALESCE(' ' || NEW.version, '') || ' de ' || NEW.service,
          NEW.occurred_at,
          CASE WHEN NEW.kind = 'ci' THEN 'remember' ELSE 'digest' END,
          CASE WHEN NEW.kind = 'ci' THEN 'ci_result' ELSE 'change_recorded' END,
          CASE WHEN NEW.kind = 'ci'
            THEN 'Resultado de CI guardado como contexto para las investigaciones.'
            WHEN NEW.status = 'failed' THEN 'Se registró como fallido; va al resumen.'
            ELSE 'Registrado; se vigila en silencio y solo te escribo si algo se rompe.' END)
        ON CONFLICT ON CONSTRAINT uq_event_decision DO NOTHING;
        RETURN NULL;
      END $$""")
    op.execute("""CREATE TRIGGER change_events_decision AFTER INSERT ON incident.change_events
      FOR EACH ROW EXECUTE FUNCTION incident.decide_change_event()""")

    # The #766 trigger keeps its name and timing; its function now asks the policy first.
    op.execute("""CREATE OR REPLACE FUNCTION incident.enqueue_dispatch_chat_messages()
      RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE
        receipt jsonb := NEW.payload -> 'dispatch_receipt';
        state jsonb;
        started_by text;
        action text;
        pending boolean;
        episodes int;
        firing int;
        lasted text;
        verdict text;
        rule text;
        reason text;
      BEGIN
        SELECT document ->> 'actor' INTO started_by FROM incident.decisions
        WHERE run_id = NEW.run_id ORDER BY decided_at, decision_id LIMIT 1;
        IF receipt ->> 'phase' = 'intent' THEN
          IF started_by IS DISTINCT FROM 'system' THEN
            INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
            SELECT chat_id, 'investigation_ack', 'investigation_ack:' || NEW.run_id,
                   jsonb_build_object('incident_id', NEW.incident_id, 'run_id', NEW.run_id,
                                      'event_id', NEW.event_id)
            FROM incident.chat_links
            ON CONFLICT (chat_id, dedup_key) DO NOTHING;
          END IF;
          RETURN NULL;
        ELSIF receipt ->> 'phase' IS DISTINCT FROM 'outcome' THEN
          RETURN NULL;
        END IF;
        SELECT payload -> 'outcome' ->> 'action' INTO action FROM incident.run_events
        WHERE run_id = NEW.run_id AND kind = 'investigation_result'
        ORDER BY sequence DESC LIMIT 1;
        pending := receipt ->> 'status' IS DISTINCT FROM 'success' OR action IS NULL
                   OR action IN ('propose_mitigation', 'request_human');
        SELECT count(*), count(*) FILTER (WHERE status = 'firing'),
               incident.lasted(max(resolved_at - starts_at))
        INTO episodes, firing, lasted
        FROM incident.alert_episodes WHERE incident_id = NEW.incident_id;
        IF started_by IS DISTINCT FROM 'system' THEN
          verdict := 'interrupt'; rule := 'requested';
          reason := 'La pidió una persona: se le responde con el resultado.';
        ELSIF episodes > 0 AND firing = 0 THEN
          verdict := 'digest'; rule := 'recovered_before_result';
          reason := 'Se recuperó sola ' || lasted || ', antes de terminar la investigación.';
        ELSIF pending THEN
          verdict := 'interrupt'; rule := 'sustained_pending_decision';
          reason := 'La alerta sigue activa y ' || CASE action
            WHEN 'propose_mitigation' THEN 'hay una mitigación esperando tu decisión.'
            WHEN 'request_human' THEN 'la investigación necesita a una persona.'
            ELSE 'la investigación no llegó a una conclusión.' END;
        ELSE
          verdict := 'digest'; rule := 'concluded_without_decision';
          reason := 'La investigación terminó sin nada que decidir; va al resumen.';
        END IF;
        SELECT i.state INTO state FROM incident.incidents i
        WHERE i.incident_id = NEW.incident_id;
        INSERT INTO incident.event_decisions (event_kind, event_id, service, incident_id, title,
          occurred_at, decision, rule, reason)
        VALUES ('investigation', NEW.run_id, state -> 'alert' ->> 'service', NEW.incident_id,
          'Investigación de ' || COALESCE(state -> 'alert' ->> 'summary', NEW.incident_id),
          NEW.occurred_at, verdict, rule, reason)
        ON CONFLICT ON CONSTRAINT uq_event_decision DO NOTHING;
        -- A pending mitigation is asked by #767's decision message, when that revision exists.
        IF verdict = 'interrupt' AND NOT (action = 'propose_mitigation' AND started_by = 'system'
            AND to_regprocedure('incident.enqueue_mitigation_decision()') IS NOT NULL) THEN
          INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
          SELECT chat_id, 'investigation_conclusion', 'investigation_conclusion:' || NEW.run_id,
                 jsonb_build_object('incident_id', NEW.incident_id, 'run_id', NEW.run_id,
                                    'event_id', NEW.event_id)
          FROM incident.chat_links
          ON CONFLICT (chat_id, dedup_key) DO NOTHING;
        END IF;
        RETURN NULL;
      END $$""")

    op.execute(
        "CREATE OR REPLACE FUNCTION incident.enqueue_mitigation_decision() RETURNS trigger "
        f"LANGUAGE plpgsql AS $${_ENQUEUE_DECISION_767.format(gate=_INTERRUPT_GATE)} $$"
    )

    for function in ("lasted(interval)", "decide_alert_episode()", "decide_change_event()"):
        op.execute(f"ALTER FUNCTION incident.{function} OWNER TO sre_incident_owner")
    op.execute("ALTER TABLE incident.event_decisions OWNER TO sre_incident_owner")
    op.execute("GRANT SELECT ON incident.event_decisions TO sre_incident_reader")
    op.execute("GRANT SELECT, INSERT ON incident.event_decisions TO sre_incident_runtime")


def downgrade() -> None:
    op.execute(
        "CREATE OR REPLACE FUNCTION incident.enqueue_mitigation_decision() RETURNS trigger "
        f"LANGUAGE plpgsql AS $${_ENQUEUE_DECISION_767.format(gate='')} $$"
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION incident.enqueue_dispatch_chat_messages() RETURNS trigger "
        f"LANGUAGE plpgsql AS $${_ENQUEUE_766} $$"
    )
    op.execute("DROP TRIGGER change_events_decision ON incident.change_events")
    op.execute("DROP FUNCTION incident.decide_change_event()")
    op.execute("DROP TRIGGER alert_episodes_decision ON incident.alert_episodes")
    op.execute("DROP FUNCTION incident.decide_alert_episode()")
    op.execute("DROP FUNCTION incident.lasted(interval)")
    op.execute("DROP TABLE incident.event_decisions")
