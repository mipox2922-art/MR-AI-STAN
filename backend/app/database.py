from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def normalize_database_url(database_url: str) -> str:
    """Normalize Supabase/Postgres URLs for SQLAlchemy + psycopg."""
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

    if database_url.startswith("postgresql+psycopg://"):
        url = make_url(database_url)
        if "sslmode" not in url.query:
            url = url.update_query_dict({"sslmode": "require"})
        database_url = url.render_as_string(hide_password=False)

    return database_url


DATABASE_URL = normalize_database_url(settings.database_url)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
