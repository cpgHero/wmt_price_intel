import pytest


def test_worker_package_is_importable() -> None:
    import rci_worker

    assert rci_worker.__doc__


def test_fake_provider_is_available_outside_production() -> None:
    from rci_worker.main import _collection_provider_mode

    assert _collection_provider_mode(app_env="development", configured=None) == "fake"
    assert _collection_provider_mode(app_env="test", configured=" fake ") == "fake"


def test_production_worker_fails_closed_on_fake_provider() -> None:
    from rci_worker.main import _collection_provider_mode

    with pytest.raises(ValueError, match="prohibited"):
        _collection_provider_mode(app_env="production", configured="fake")


def test_production_worker_accepts_metricscart_provider() -> None:
    from rci_worker.main import _collection_provider_mode

    assert (
        _collection_provider_mode(app_env="production", configured="metricscart") == "metricscart"
    )


def test_worker_rejects_unknown_provider() -> None:
    from rci_worker.main import _collection_provider_mode

    with pytest.raises(ValueError, match="must be"):
        _collection_provider_mode(app_env="development", configured="unknown")
