import ssl

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def normalize_database_url(database_url: str) -> str:
    """Normalize Postgres URLs for SQLAlchemy's pure-Python pg8000 driver."""
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]

    for old_scheme in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if database_url.startswith(old_scheme):
            database_url = "postgresql+pg8000://" + database_url[len(old_scheme):]
            break

    if database_url.startswith("postgresql://"):
        database_url = "postgresql+pg8000://" + database_url[len("postgresql://"):]

    if database_url.startswith("postgresql+pg8000://"):
        url = make_url(database_url)
        # sslmode belongs to libpq-based drivers; pg8000 gets TLS via ssl_context.
        query = {key: value for key, value in url.query.items() if key != "sslmode"}
        url = url.set(query=query)
        database_url = url.render_as_string(hide_password=False)

    return database_url


def create_postgres_ssl_context() -> ssl.SSLContext:
    """Create a TLS context that verifies the database certificate and hostname."""
    return ssl.create_default_context()


DATABASE_URL = normalize_database_url(settings.database_url)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql+pg8000://"):
    # Never disable certificate verification for a database connection.
    # If a provider uses a private CA, configure that CA in the runtime trust store.
    connect_args = {"ssl_context": create_postgres_ssl_context()}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=1 if DATABASE_URL.startswith("postgresql+pg8000://") else 5,
    max_overflow=0 if DATABASE_URL.startswith("postgresql+pg8000://") else 10,
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
