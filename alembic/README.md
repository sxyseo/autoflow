# Alembic Database Migrations

This directory contains database migration scripts for Autoflow.

## Setup

Alembic is configured to use the database URL from the `AUTOFLOW_DATABASE_URL` environment variable, or defaults to SQLite (`./autoflow.db`) for local development.

## Configuration

- **`alembic.ini`**: Main Alembic configuration file
- **`env.py`**: Migration environment setup
- **`script.py.mako`**: Template for new migration files
- **`versions/`**: Directory containing migration scripts

## Common Commands

```bash
# Create a new migration
alembic revision -m "description of changes"

# Create a migration based on current models (autogenerate)
alembic revision --autogenerate -m "add users table"

# Apply all migrations
alembic upgrade head

# Apply migrations to a specific version
alembic upgrade <revision_id>

# Rollback one migration
alembic downgrade -1

# Rollback to a specific version
alembic downgrade <revision_id>

# View migration history
alembic history

# View current version
alembic current

# Show the SQL for a migration (without running it)
alembic upgrade head --sql
```

## Environment Variables

- **`AUTOFLOW_DATABASE_URL`**: Database connection URL
  - PostgreSQL: `postgresql://user:pass@localhost/dbname`
  - SQLite: `sqlite:///./autoflow.db` (default)

- **`AUTOFLOW_DATABASE_ECHO`**: Set to `1` or `true` to log all SQL statements

## Migration Workflow

1. Make changes to `autoflow/db/models.py`
2. Generate a migration: `alembic revision --autogenerate -m "description"`
3. Review the generated migration in `alembic/versions/`
4. Apply the migration: `alembic upgrade head`

## Best Practices

- Always review auto-generated migrations before applying them
- Write descriptive migration messages
- Never modify existing migrations that have been deployed
- Test migrations on a copy of production data before deploying
- Keep migrations reversible (always implement `downgrade()`)

## Troubleshooting

### Migration conflicts

If multiple developers create migrations with the same revision ID, you'll need to resolve conflicts manually:

1. Identify conflicting migrations in `alembic/versions/`
2. Create a new migration that resolves the differences
3. Remove or rename the conflicting migration files

### Database state mismatch

If your database state doesn't match the migration history:

1. Check current version: `alembic current`
2. Check migration history: `alembic history`
3. Manually stamp the database to a specific version:
   ```bash
   alembic stamp <revision_id>
   ```

### SQLite limitations

- SQLite has limited ALTER TABLE support
- Some schema changes require recreating tables
- Alembic uses "batch mode" for SQLite to work around limitations
- Consider using PostgreSQL for production

## Related Files

- `autoflow/db/models.py`: SQLAlchemy ORM models
- `autoflow/db/session.py`: Database session management
- `pyproject.toml`: Project dependencies including alembic
