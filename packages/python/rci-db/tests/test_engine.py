from rci_db import normalize_database_url


def test_normalizes_railway_database_url() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@postgres.internal:5432/railway")
        == "postgresql+psycopg://user:pass@postgres.internal:5432/railway"
    )


def test_normalizes_legacy_postgres_scheme() -> None:
    assert normalize_database_url("postgres://localhost/rci") == (
        "postgresql+psycopg://localhost/rci"
    )


def test_preserves_explicit_driver() -> None:
    url = "postgresql+psycopg://localhost/rci"
    assert normalize_database_url(url) == url
