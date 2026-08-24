import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from sre_agent.persistence.models import Base

config = context.config
url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", url)


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    engine = engine_from_config(section, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, transactional_ddl=True
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
