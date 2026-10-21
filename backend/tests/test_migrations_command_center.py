from sqlalchemy import create_engine, text

from app.migrations import run_schema_migrations


def test_legacy_sqlite_schema_is_upgraded_and_unverified_done_is_downgraded():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(255), created_at TIMESTAMP)"))
        conn.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(255), description TEXT, status VARCHAR(30), progress INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)"))
        conn.execute(text("CREATE TABLE task_steps (id INTEGER PRIMARY KEY, task_id INTEGER, position INTEGER, title VARCHAR(255), state VARCHAR(20), evidence TEXT)"))
        conn.execute(text("INSERT INTO tasks (id, user_id, title, status, progress) VALUES (1, 1, 'Legacy', 'COMPLETED', 100)"))

    run_schema_migrations(engine)
    run_schema_migrations(engine)

    with engine.connect() as conn:
        task = conn.execute(text("SELECT status, progress, source FROM tasks WHERE id=1")).one()
        assert task.status == "WAITING_FOR_VERIFICATION"
        assert task.progress == 0
        assert task.source == "unknown"
        convo_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(conversations)")).all()}
        assert "session_id" in convo_columns
        assert conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='ix_conversations_user_session'")).scalar_one() == 1
