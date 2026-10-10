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


def create_postgres_ssl_context(ca_certificate: str | None = None) -> ssl.SSLContext:
    """Create a verified TLS context, optionally trusting a provider CA certificate.

    The argument may be a path to a PEM file or the PEM certificate text itself.
    Certificate and hostname verification remain enabled in both cases.
    """
    context = ssl.create_default_context()
    configured_ca = (
        settings.database_ssl_ca_cert if ca_certificate is None else ca_certificate
    ).strip()
    if configured_ca:
        if "-----BEGIN CERTIFICATE-----" in configured_ca:
            context.load_verify_locations(cadata=configured_ca)
        else:
            context.load_verify_locations(cafile=configured_ca)
    return context


DATABASE_URL = normalize_database_url(settings.database_url)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql+pg8000://"):
    # Never disable certificate verification for a database connection.
    # For a private CA, provide DATABASE_SSL_CA_CERT as PEM text or a mounted PEM path.
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
