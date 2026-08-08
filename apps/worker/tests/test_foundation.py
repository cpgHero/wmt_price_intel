def test_worker_package_is_importable() -> None:
    import rci_worker

    assert rci_worker.__doc__
