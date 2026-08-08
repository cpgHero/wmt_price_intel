from rci_core import AppSettings


def test_settings_use_safe_development_defaults(monkeypatch) -> None:
    for name in ("APP_ENV", "APP_VERSION", "DATABASE_URL", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)

    settings = AppSettings.from_env()

    assert settings.app_env == "development"
    assert settings.app_version == "0.1.0"
    assert settings.is_production is False


def test_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_VERSION", "9.8.7")
    monkeypatch.setenv("LOG_LEVEL", "warning")

    settings = AppSettings.from_env()

    assert settings.is_production is True
    assert settings.app_version == "9.8.7"
    assert settings.log_level == "WARNING"
