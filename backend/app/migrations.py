"""Additive, idempotent schema upgrades for existing SQLite/PostgreSQL installs."""
from sqlalchemy import inspect


COLUMN_UPGRADES = {
    "conversations": {
        "session_id": "VARCHAR(100)",
    },
    "tasks": {
        "source": "VARCHAR(20) NOT NULL DEFAULT 'boss'",
        "requested_by": "VARCHAR(100)",
        "approved_by": "INTEGER",
        "approved_at": "TIMESTAMP",
    },
}


def run_schema_migrations(engine) -> None:
    """Upgrade existing tables after metadata.create_all() created new tables."""
    with engine.begin() as connection:
        current_inspector = inspect(connection)
        for table_name, columns in COLUMN_UPGRADES.items():
            if not current_inspector.has_table(table_name):
                continue
            existing = {column["name"] for column in inspect(connection).get_columns(table_name)}
            for column_name, declaration in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"
                    )

        current_inspector = inspect(connection)
        if current_inspector.has_table("conversations"):
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_session "
                "ON conversations (user_id, session_id)"
            )

        # Legacy "completed" tasks without proof remain visible but are not verified done.
        current_inspector = inspect(connection)
        if current_inspector.has_table("tasks") and current_inspector.has_table("task_steps"):
            connection.exec_driver_sql(
                "UPDATE tasks SET status = 'WAITING_FOR_VERIFICATION', progress = 0 "
                "WHERE UPPER(status) IN ('COMPLETED', 'DONE') "
                "AND NOT EXISTS ("
                "SELECT 1 FROM task_steps s WHERE s.task_id = tasks.id "
                "AND LOWER(s.state) = 'verified' "
                "AND LENGTH(TRIM(COALESCE(s.evidence, ''))) > 0)"
            )
