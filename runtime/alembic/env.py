"""Alembic migrations environment."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.database import DatabaseClient

config = context.config
fileConfig(config.config_file_name)

def get_url():
    return os.environ.get('DATABASE_URL', 'postgresql://ai_user:changeme@localhost:5432/ai_employee')

def run_migrations_offline():
    """Run migrations in offline mode."""
    url = get_url()
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in online mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
