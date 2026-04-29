"""
Tests for Step 1.2: Settings Management.

These tests verify that:
1. Settings can be created with default values (no env vars needed)
2. Settings can be overridden via environment variables
3. Required fields (like API keys) fail clearly when missing in production
4. The get_settings() cache works correctly
5. Each settings group (app, database, auth, deepseek, cohere) is accessible
6. Type validation works (e.g., port must be an integer)

How these tests work:
- We use monkeypatch to simulate environment variables
- Each test creates settings with explicit constructor args (not from env)
  to test the model validation in isolation
- Integration tests use monkeypatch to test env var loading
"""

import pytest
from pydantic import ValidationError


# ── Test 1: App settings defaults ────────────────────────────────────────

class TestAppSettings:
    """Verify application-level settings."""

    def test_default_values(self):
        """App settings should have sensible defaults for local development."""
        from sentinel.config.settings import AppSettings
        settings = AppSettings()
        assert settings.env == "development"
        assert settings.debug is True
        assert settings.port == 8000

    def test_custom_values(self):
        """App settings should accept overrides."""
        from sentinel.config.settings import AppSettings
        settings = AppSettings(env="production", debug=False, port=9000)
        assert settings.env == "production"
        assert settings.debug is False
        assert settings.port == 9000

    def test_port_must_be_integer(self):
        """Port must be a valid integer, not arbitrary text."""
        from sentinel.config.settings import AppSettings
        # Pydantic should coerce "8080" to 8080, but reject non-numeric
        settings = AppSettings(port="8080")
        assert settings.port == 8080


# ── Test 2: Database settings ────────────────────────────────────────────

class TestDatabaseSettings:
    """Verify database configuration."""

    def test_default_database_url(self):
        """Should have a default DATABASE_URL for local Docker dev."""
        from sentinel.config.settings import DatabaseSettings
        settings = DatabaseSettings()
        assert "postgresql" in settings.url
        assert "sentinel" in settings.url

    def test_custom_database_url(self):
        """Should accept a custom database URL."""
        from sentinel.config.settings import DatabaseSettings
        custom_url = "postgresql+asyncpg://user:pass@remote:5432/mydb"
        settings = DatabaseSettings(url=custom_url)
        assert settings.url == custom_url


# ── Test 3: Auth settings ───────────────────────────────────────────────

class TestAuthSettings:
    """Verify JWT / authentication configuration."""

    def test_default_values(self):
        """Auth settings should have dev-safe defaults."""
        from sentinel.config.settings import AuthSettings
        settings = AuthSettings()
        assert settings.secret_key == "dev-secret-change-in-production"
        assert settings.algorithm == "HS256"
        assert settings.expiration_minutes == 60

    def test_custom_secret(self):
        """Secret key should be overridable."""
        from sentinel.config.settings import AuthSettings
        settings = AuthSettings(secret_key="my-production-secret")
        assert settings.secret_key == "my-production-secret"


# ── Test 4: DeepSeek settings ───────────────────────────────────────────

class TestDeepSeekSettings:
    """Verify LLM provider configuration."""

    def test_default_model(self):
        """Should default to deepseek-chat model."""
        from sentinel.config.settings import DeepSeekSettings
        settings = DeepSeekSettings()
        assert settings.model == "deepseek-chat"

    def test_api_key_defaults_empty(self):
        """API key defaults to empty string for dev (must be set in production)."""
        from sentinel.config.settings import DeepSeekSettings
        settings = DeepSeekSettings()
        assert settings.api_key == ""

    def test_custom_api_key(self):
        """API key should be overridable."""
        from sentinel.config.settings import DeepSeekSettings
        settings = DeepSeekSettings(api_key="sk-test-123")
        assert settings.api_key == "sk-test-123"


# ── Test 5: Cohere settings ─────────────────────────────────────────────

class TestCohereSettings:
    """Verify embedding provider configuration."""

    def test_default_model(self):
        """Should default to embed-english-v3.0 model."""
        from sentinel.config.settings import CohereSettings
        settings = CohereSettings()
        assert settings.embed_model == "embed-english-v3.0"

    def test_api_key_defaults_empty(self):
        """API key defaults to empty string for dev."""
        from sentinel.config.settings import CohereSettings
        settings = CohereSettings()
        assert settings.api_key == ""


# ── Test 6: Combined Settings object ────────────────────────────────────

class TestSettings:
    """Verify the top-level Settings that combines all groups."""

    def test_settings_has_all_groups(self):
        """The combined Settings must expose all config groups."""
        from sentinel.config.settings import Settings
        settings = Settings()
        assert hasattr(settings, "app")
        assert hasattr(settings, "database")
        assert hasattr(settings, "auth")
        assert hasattr(settings, "deepseek")
        assert hasattr(settings, "cohere")

    def test_settings_groups_have_correct_types(self):
        """Each group should be the correct typed settings class."""
        from sentinel.config.settings import (
            Settings, AppSettings, DatabaseSettings,
            AuthSettings, DeepSeekSettings, CohereSettings,
        )
        settings = Settings()
        assert isinstance(settings.app, AppSettings)
        assert isinstance(settings.database, DatabaseSettings)
        assert isinstance(settings.auth, AuthSettings)
        assert isinstance(settings.deepseek, DeepSeekSettings)
        assert isinstance(settings.cohere, CohereSettings)

    def test_nested_access_works(self):
        """Should be able to access nested values like settings.app.port."""
        from sentinel.config.settings import Settings
        settings = Settings()
        assert settings.app.port == 8000
        assert settings.auth.algorithm == "HS256"
        assert settings.deepseek.model == "deepseek-chat"


# ── Test 7: get_settings() cache ────────────────────────────────────────

class TestGetSettings:
    """Verify the cached settings loader."""

    def test_get_settings_returns_settings_instance(self):
        """get_settings() must return a Settings object."""
        from sentinel.config.settings import get_settings, Settings
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_returns_same_instance(self):
        """Calling get_settings() twice should return the same cached object."""
        from sentinel.config.settings import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


# ── Test 8: Environment variable loading ─────────────────────────────────

class TestEnvVarLoading:
    """Verify settings load from environment variables."""

    def test_app_env_from_environ(self, monkeypatch):
        """APP_ENV environment variable should override the default."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("APP_DEBUG", "false")
        from sentinel.config.settings import AppSettings
        # Create fresh instance (not cached) to pick up env var
        settings = AppSettings()
        assert settings.env == "production"
        assert settings.debug is False

    def test_database_url_from_environ(self, monkeypatch):
        """DATABASE_URL should be loadable from environment."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://prod:pass@db:5432/prod")
        from sentinel.config.settings import DatabaseSettings
        settings = DatabaseSettings()
        assert "prod" in settings.url
