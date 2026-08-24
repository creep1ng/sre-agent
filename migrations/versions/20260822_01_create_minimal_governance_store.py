from alembic import op

revision = "20260822_01"
down_revision = None
branch_labels = None
depends_on = None

TABLES = (
    """CREATE TABLE principals (
      principal_id varchar(64) PRIMARY KEY, kind varchar(16) NOT NULL,
      display_name varchar(200) NOT NULL, status varchar(16) NOT NULL,
      created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
      CONSTRAINT ck_principals_kind CHECK (kind IN ('human','agent')),
      CONSTRAINT ck_principals_status CHECK (status IN ('active','inactive')),
      CONSTRAINT ck_principals_lifecycle CHECK (updated_at >= created_at))""",
    """CREATE TABLE credentials (
      credential_id varchar(64) PRIMARY KEY, principal_id varchar(64) NOT NULL
        REFERENCES principals(principal_id),
      prefix varchar(16) NOT NULL, key_hash varchar(512) NOT NULL,
      status varchar(16) NOT NULL, created_at timestamptz NOT NULL,
      expires_at timestamptz, revoked_at timestamptz,
      CONSTRAINT uq_credentials_prefix UNIQUE (prefix),
      CONSTRAINT ck_credentials_status CHECK (status IN ('active','revoked')),
      CONSTRAINT ck_credentials_lifecycle CHECK ((status='active' AND revoked_at IS NULL) OR
        (status='revoked' AND revoked_at IS NOT NULL AND revoked_at >= created_at)),
      CONSTRAINT ck_credentials_expiry CHECK (expires_at IS NULL OR expires_at > created_at))""",
    """CREATE TABLE resources (
      resource_type varchar(32) NOT NULL, resource_id varchar(200) NOT NULL,
      status varchar(16) NOT NULL, model_alias_id varchar(64), alias varchar(64),
      concrete_model varchar(200), router varchar(100), inference_provider varchar(100),
      PRIMARY KEY (resource_type, resource_id),
      CONSTRAINT uq_resources_model_alias_id UNIQUE (model_alias_id),
      CONSTRAINT uq_resources_alias UNIQUE (alias),
      CONSTRAINT ck_resources_type CHECK (resource_type IN
        ('llm_model','mcp_server','mcp_tool','skill','bok_collection')),
      CONSTRAINT ck_resources_status CHECK (status IN ('active','inactive')),
      CONSTRAINT ck_resources_llm_assignment CHECK
        ((resource_type='llm_model' AND model_alias_id IS NOT NULL AND alias IS NOT NULL AND
          concrete_model IS NOT NULL AND router='openrouter' AND inference_provider IS NOT NULL) OR
         (resource_type<>'llm_model' AND model_alias_id IS NULL AND alias IS NULL AND
          concrete_model IS NULL AND router IS NULL AND inference_provider IS NULL)))""",
    """CREATE TABLE grants (
      grant_id varchar(64) PRIMARY KEY, principal_id varchar(64) NOT NULL
        REFERENCES principals(principal_id),
      action varchar(64) NOT NULL, resource_type varchar(32) NOT NULL,
      resource_id varchar(200) NOT NULL, effect varchar(16) NOT NULL,
      status varchar(16) NOT NULL, created_at timestamptz NOT NULL,
      FOREIGN KEY (resource_type,resource_id) REFERENCES resources(resource_type,resource_id),
      CONSTRAINT uq_grants_direct UNIQUE (principal_id,action,resource_type,resource_id),
      CONSTRAINT ck_grants_effect CHECK (effect='allow'),
      CONSTRAINT ck_grants_status CHECK (status IN ('active','revoked')))""",
    """CREATE TABLE audit_events (
      event_id varchar(40) PRIMARY KEY, occurred_at timestamptz NOT NULL,
      operation varchar(32) NOT NULL, action varchar(32) NOT NULL, stage varchar(32) NOT NULL,
      outcome varchar(16) NOT NULL, reason_code varchar(64), response_status integer NOT NULL,
      retryable boolean NOT NULL, correlation jsonb NOT NULL, identity jsonb, resource jsonb,
      model_alias_ref jsonb, policy_decision jsonb, routing jsonb, untrusted_input jsonb,
      redaction jsonb NOT NULL, content_state varchar(32) NOT NULL, redacted_content jsonb,
      authoritative_acceptance varchar(16) NOT NULL, ordinary_result varchar(16) NOT NULL,
      exporter_result varchar(16) NOT NULL, correction_of_event_id varchar(40),
      CONSTRAINT ck_audit_events_operation CHECK (operation IN ('audit.accept','audit.export',
        'audit.project','audit.redact','credentials.authenticate','responses.create')),
      CONSTRAINT ck_audit_events_action CHECK (action IN
        ('authenticate','export','invoke','persist','read_metadata','redact')),
      CONSTRAINT ck_audit_events_stage CHECK (stage IN ('validation','authentication',
        'authorization','routing','upstream','response','audit')),
      CONSTRAINT ck_audit_events_outcome CHECK (outcome IN ('success','denied','error')),
      CONSTRAINT ck_audit_events_reason_code CHECK (reason_code IS NULL OR reason_code IN
        ('audit_unavailable','authentication_failed','contract_validation_failed','grant_matched',
         'no_matching_grant','redaction_failed','redaction_uncertain','routing_unavailable',
         'upstream_failed','upstream_invalid','upstream_unavailable')),
      CONSTRAINT ck_audit_events_response CHECK (response_status BETWEEN 100 AND 599),
      CONSTRAINT ck_audit_events_content_state CHECK
        (content_state IN ('absent','redacted','redaction_failed')),
      CONSTRAINT ck_audit_events_acceptance CHECK
        (authoritative_acceptance IN ('accepted','rejected')),
      CONSTRAINT ck_audit_events_result CHECK (ordinary_result IN ('released','suppressed')),
      CONSTRAINT ck_audit_events_exporter CHECK
        (exporter_result IN ('not_attempted','succeeded','failed')))""",
)


def upgrade() -> None:
    for statement in TABLES:
        op.execute(statement)
    op.execute("""CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'audit_events are append-only'; END $$""")
    op.execute("""CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
      FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()""")


def downgrade() -> None:
    op.execute("DROP TABLE audit_events, grants, credentials, resources, principals")
    op.execute("DROP FUNCTION reject_audit_mutation()")
