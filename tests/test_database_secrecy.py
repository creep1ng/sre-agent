from sqlalchemy.exc import StatementError

from sre_agent.persistence.database import Database


def test_database_hides_bound_parameters_in_sqlalchemy_errors() -> None:
    database = Database("postgresql://operator:password@localhost:5432/sre_agent")
    try:
        assert database.engine.sync_engine.hide_parameters is True
        secret = "scrypt$never-render-this-key-hash"
        error = StatementError(
            "database operation failed",
            "INSERT INTO credentials (key_hash) VALUES (%(key_hash)s)",
            {"key_hash": secret},
            RuntimeError("safe driver detail"),
            hide_parameters=database.engine.sync_engine.hide_parameters,
        )
        rendered = str(error)
        assert secret not in rendered
        assert "[SQL parameters hidden due to hide_parameters=True]" in rendered
    finally:
        database.engine.sync_engine.dispose()
