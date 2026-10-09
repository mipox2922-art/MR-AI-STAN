from app.database import normalize_database_url


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
