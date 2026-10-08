from app.database import normalize_database_url


def test_normalize_postgres_url_for_psycopg():
    url = normalize_database_url(
        "postgresql://postgres.project-ref:secret@pooler.example.com:5432/postgres"
    )

    assert url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url
    assert "postgres.project-ref" in url
