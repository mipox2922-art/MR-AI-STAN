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


def postgres_connect_args(
    database_url: str,
    ca_certificate: str | None = None,
) -> dict:
    """Choose safe transport settings for the configured PostgreSQL URL.

    Render's internal Postgres hostname (dpg-* without a public DNS suffix) uses
    Render's private network and intentionally has no sslmode query parameter.
    Do not force TLS on that route: Render internal endpoints can use
    self-signed certificates, so verified TLS will fail instead of connecting.
    External PostgreSQL endpoints continue to use verified TLS; an explicit CA
    can be supplied with DATABASE_SSL_CA_CERT.
    """
    parsed = make_url(database_url)
    sslmode = str(parsed.query.get("sslmode", "")).lower()
    configured_ca = (
        settings.database_ssl_ca_cert if ca_certificate is None else ca_certificate
    ).strip()
    host = (parsed.host or "").lower()
    render_internal_host = host.startswith("dpg-") and "." not in host

    if sslmode == "disable":
        return {}

    # The Blueprint's fromDatabase.connectionString is an internal URL without
    # sslmode; use the private network without TLS unless the operator explicitly
    # requests TLS or supplies a CA certificate.
    if render_internal_host and sslmode not in {"require", "verify-ca", "verify-full"} and not configured_ca:
        return {}

    return {"ssl_context": create_postgres_ssl_context(configured_ca)}


DATABASE_URL = normalize_database_url(settings.database_url)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql+pg8000://"):
    connect_args = postgres_connect_args(settings.database_url)

def database_pool_options(database_url: str) -> dict[str, int]:
    """Return bounded pool settings appropriate for the configured database.

    The hosted dashboard polls several authenticated endpoints concurrently while
    the scheduler also uses PostgreSQL. A one-connection pool serializes those
    requests and can make health checks fail while another request is active.
    Keep a modest pool with limited overflow so the free Render database is not
    flooded, and fail a checkout quickly rather than stalling API calls for 30s.
    """
    if database_url.startswith("postgresql+pg8000://"):
        return {
            "pool_size": 5,
            "max_overflow": 5,
            "pool_timeout": 10,
            "pool_recycle": 1800,
        }
    return {"pool_size": 5, "max_overflow": 10}


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    **database_pool_options(DATABASE_URL),
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
