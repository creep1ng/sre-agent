import os

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, event, pool, text
from sqlalchemy.schema import AddConstraint

from sre_agent.persistence.models import Base

config = context.config
url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", url)


def integrated_upgrade():
    """Recognize only a forward upgrade into the explicitly supported union head."""
    script = ScriptDirectory.from_config(config)
    destination = context.get_context().opts.get("destination_rev")
    target = script.as_revision_number(destination) if destination else None
    if target != "20260929_18":
        return None
    current = set(context.get_context().get_current_heads())
    ancestors = {revision.revision for revision in script.iterate_revisions(target, "base")}
    if current == {target} or not current <= ancestors:
        return None
    # An intermediate vocabulary narrower than the union cannot be validated against rows
    # already written by a sibling history, so it is created NOT VALID. The union itself is
    # a superset of every ancestor vocabulary, so no existing row can violate it and it is
    # always validated. Keying on the union text keeps an ancestor that already declares the
    # full vocabulary on the validating path.
    # Heads 20260929_17 and 20260929_18 only add reservation tables and the
    # reason vocabulary, leaving the operation vocabulary untouched, so the
    # union is read from 20261001_02, the nearest ancestor that declares it.
    union = script.get_revision("20261001_02").module.NEW_OPERATION
    legacy_checks = {
        script.get_revision(revision).module.NEW_OPERATION
        for revision in (
            "20260926_14",
            "20260926_15",
            "20260926_16",
            "20260929_16",
            "20260930_18",
            "20260930_19",
            "20261001_01",
            "20261001_02",
        )
    } - {union}
    return target, legacy_checks


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    engine = engine_from_config(section, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, transactional_ddl=True
        )
        with context.begin_transaction():
            integration = integrated_upgrade()
            if integration is None:
                context.run_migrations()
                return
            target, legacy_checks = integration

            def defer_legacy_scan(connection, clause, multiparams, params, options):
                if isinstance(clause, AddConstraint):
                    constraint = clause.element
                    if (
                        constraint.table.schema is None
                        and constraint.table.name == "audit_events"
                        and constraint.name == "ck_audit_events_operation"
                        and str(constraint.sqltext) in legacy_checks
                    ):
                        constraint.dialect_options["postgresql"]["not_valid"] = True

            # Existing rows may span sibling histories; only the final bounded union
            # may commit. The connection listener never participates in old targets.
            event.listen(connection, "before_execute", defer_legacy_scan)
            try:
                context.run_migrations()
                validated = connection.scalar(
                    text(
                        "SELECT convalidated FROM pg_constraint "
                        "WHERE conrelid='audit_events'::regclass "
                        "AND conname='ck_audit_events_operation'"
                    )
                )
                if context.get_context().get_current_heads() != (target,) or validated is not True:
                    raise RuntimeError("audit migration integration incomplete")
            finally:
                event.remove(connection, "before_execute", defer_legacy_scan)


run_migrations_online()
