"""
Alembic Environment Configuration

Configures the Alembic migration environment for Autoflow.
This file is executed when running Alembic commands.

The environment setup:
- Loads database configuration from environment variables
- Connects to the database using SQLAlchemy
- Imports all ORM models for autogenerate support
- Provides the migration context
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import the database models and Base
# This is required for autogenerate to detect model changes
from autoflow.db.models import Base
from autoflow.db.session import DEFAULT_DATABASE_URL, ENV_DATABASE_URL

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL from environment variable or use the default
# Priority:
# 1. sqlalchemy.url from alembic.ini (can be overridden)
# 2. AUTOFLOW_DATABASE_URL environment variable
# 3. Default SQLite database
database_url = os.environ.get(ENV_DATABASE_URL)

if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
elif config.get_main_option("sqlalchemy.url") == "driver://user:pass@localhost/dbname":
    # Use default URL if not explicitly set
    config.set_main_option("sqlalchemy.url", DEFAULT_DATABASE_URL)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# Other values from the config can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Enable batch mode for SQLite compatibility
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context.
    """
    # Handle SQLite special case for connection pooling
    connect_args = {}
    database_url = config.get_main_option("sqlalchemy.url")

    if database_url and database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    # Create the engine with appropriate configuration
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool if database_url and database_url.startswith("sqlite") else pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Enable batch mode for SQLite compatibility
            compare_type=True,  # Detect column type changes
            compare_server_default=True,  # Detect server default changes
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
