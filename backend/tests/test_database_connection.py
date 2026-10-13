import ssl

from app.database import (
    create_postgres_ssl_context,
    database_pool_options,
    normalize_database_url,
    postgres_connect_args,
)


def test_normalize_postgres_url_for_pg8000_and_tls():
    url = normalize_database_url(
        "postgresql://postgres.project-ref:secret@pooler.example.com:5432/postgres"
    )

    assert url.startswith("postgresql+pg8000://")
    assert "sslmode=" not in url
    assert "postgres.project-ref" in url


def test_normalize_existing_psycopg_url_to_pg8000():
    url = normalize_database_url(
        "postgresql+psycopg://postgres.project-ref:secret@pooler.example.com:5432/postgres?sslmode=require"
    )

    assert url.startswith("postgresql+pg8000://")
    assert "sslmode=" not in url


def test_render_internal_postgres_uses_private_network_without_forced_tls():
    connect_args = postgres_connect_args(
        "postgresql://mr_ai_stan_db_user:secret@dpg-db6inl5g1s2s739fdf40-a/mr_ai_stan_db"
    )

    assert connect_args == {}


def test_external_postgres_url_keeps_verified_tls():
    connect_args = postgres_connect_args(
        "postgresql://postgres.project-ref:secret@pooler.example.com:5432/postgres"
    )

    assert isinstance(connect_args["ssl_context"], ssl.SSLContext)
    assert connect_args["ssl_context"].verify_mode == ssl.CERT_REQUIRED
    assert connect_args["ssl_context"].check_hostname is True


def test_explicit_tls_request_for_render_internal_postgres_is_respected():
    connect_args = postgres_connect_args(
        "postgresql://mr_ai_stan_db_user:secret@dpg-db6inl5g1s2s739fdf40-a/mr_ai_stan_db?sslmode=require"
    )

    assert isinstance(connect_args["ssl_context"], ssl.SSLContext)


def test_postgres_tls_verifies_certificate_and_hostname():
    context = create_postgres_ssl_context()

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_postgres_tls_can_load_an_explicit_pem_ca(monkeypatch):
    class FakeContext:
        loaded = None

        def load_verify_locations(self, *, cadata=None, cafile=None):
            self.loaded = {"cadata": cadata, "cafile": cafile}

    fake_context = FakeContext()
    monkeypatch.setattr(
        "app.database.ssl.create_default_context",
        lambda: fake_context,
    )
    pem = "-----BEGIN CERTIFICATE-----\nplaceholder\n-----END CERTIFICATE-----"

    result = create_postgres_ssl_context(pem)

    assert result is fake_context
    assert fake_context.loaded == {"cadata": pem, "cafile": None}



def test_postgres_pool_supports_parallel_dashboard_and_scheduler_requests():
    options = database_pool_options("postgresql+pg8000://user:secret@db.example.com/app")

    assert options["pool_size"] == 5
    assert options["max_overflow"] == 5
    assert options["pool_size"] + options["max_overflow"] == 10
    assert options["pool_timeout"] == 10
    assert options["pool_recycle"] == 1800
