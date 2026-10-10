import ssl

from app.database import create_postgres_ssl_context, normalize_database_url


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
