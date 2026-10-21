from sqlalchemy import create_engine, inspect, text

from app.migrations import run_schema_migrations


def test_migration_adds_columns_and_is_idempotent_on_existing_sqlite_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(255), created_at TIMESTAMP)")
        conn.exec_driver_sql("CREATE TABLE tasks (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(255) NOT NULL, status VARCHAR(30), progress INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)")
        conn.exec_driver_sql("CREATE TABLE task_steps (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, state VARCHAR(20), evidence TEXT)")
        conn.exec_driver_sql("INSERT INTO tasks (id, user_id, title, status, progress) VALUES (1,1,'Old completed task','COMPLETED',100)")
    run_schema_migrations(engine)
    run_schema_migrations(engine)
    with engine.connect() as conn:
        columns = {row["name"] for row in inspect(conn).get_columns("tasks")}
        convo_columns = {row["name"] for row in inspect(conn).get_columns("conversations")}
        assert {"source", "requested_by", "approved_by", "approved_at"} <= columns
        assert "session_id" in convo_columns
        status, progress = conn.execute(text("SELECT status, progress FROM tasks WHERE id=1")).one()
        assert status == "WAITING_FOR_VERIFICATION"
        assert progress == 0
