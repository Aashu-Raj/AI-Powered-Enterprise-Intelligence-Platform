"""
database/migrations/env.py

Alembic environment configuration.
Supports both offline (generate SQL) and online (apply to DB) modes.
Uses the SYNC database URL for Alembic CLI compatibility.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Add project root to Python path ──────────────────────────────────────────
# This ensures Alembic can import our models and settings
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# ── Import models so Alembic autogenerate discovers all tables ────────────────
from database.base import Base  # noqa: E402
import database.models  # noqa: E402, F401 — registers all models on Base.metadata

from shared.config.settings import settings  # noqa: E402

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from settings (sync driver for Alembic)
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

target_metadata = Base.metadata


# ─────────────────────────────────────────────────────────────────────────────
# Offline mode: generate SQL script without connecting to DB
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Online mode: apply migrations directly to the database
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool for migration scripts (no connection reuse)
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
