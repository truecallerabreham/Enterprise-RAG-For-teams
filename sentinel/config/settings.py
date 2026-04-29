"""
Sentinel Settings Management.

This module provides typed, validated configuration for the entire application.
It solves the problem of scattered, unvalidated config by centralizing all
settings into Pydantic models that:

1. Load values from environment variables automatically
2. Validate types (port must be int, debug must be bool, etc.)
3. Provide sensible defaults for local development
4. Fail fast with clear errors if required config is missing

HOW IT WORKS (step by step):

1. Each settings group (App, Database, Auth, etc.) is a Pydantic BaseSettings
   class. Pydantic BaseSettings reads from environment variables automatically
   using the `env_prefix` to namespace them:
     - AppSettings with env_prefix="APP_" reads APP_ENV, APP_DEBUG, APP_PORT
     - DatabaseSettings reads DATABASE_URL
     - etc.

2. The top-level `Settings` class composes all groups together, so the rest
   of the app only needs one object to access any config value:
     settings.app.port
     settings.database.url
     settings.deepseek.api_key

3. `get_settings()` is a cached function that creates the Settings object
   once and reuses it. This avoids re-reading environment variables on every
   request and ensures the entire app shares one config instance.

WHY `env_prefix` MATTERS:
   Without prefixes, a field named `url` would read from env var `URL`,
   which is too generic and could collide with other tools. Prefixes
   make it explicit: DATABASE_URL, DEEPSEEK_API_KEY, etc.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# ─────────────────────────────────────────────────────────────────────────────
# Individual Settings Groups
# ─────────────────────────────────────────────────────────────────────────────


class AppSettings(BaseSettings):
    """
    Application-level settings.

    Controls the runtime environment, debug mode, and server port.
    These are the most basic settings that every app needs.

    Environment variables:
        APP_ENV  — "development", "staging", or "production"
        APP_DEBUG — "true" or "false"
        APP_PORT — integer port number
    """
    model_config = SettingsConfigDict(env_prefix="APP_")

    env: str = "development"
    debug: bool = True
    port: int = 8000


class DatabaseSettings(BaseSettings):
    """
    Database connection settings.

    Uses a single URL that includes the driver, credentials, host, and
    database name. The default points to the Docker Compose PostgreSQL
    instance defined in docker-compose.yml.

    Environment variables:
        DATABASE_URL — full connection string
    """
    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = "postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinel"


class AuthSettings(BaseSettings):
    """
    JWT authentication settings.

    Controls how dev-mode JWT tokens are created and validated.
    The secret key MUST be changed in production.

    Environment variables:
        AUTH_SECRET_KEY — signing key for JWTs
        AUTH_ALGORITHM — JWT signing algorithm (default: HS256)
        AUTH_EXPIRATION_MINUTES — token lifetime in minutes
    """
    model_config = SettingsConfigDict(env_prefix="AUTH_")

    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    expiration_minutes: int = 60


class DeepSeekSettings(BaseSettings):
    """
    DeepSeek LLM provider settings.

    Used by the answer orchestration module to generate grounded answers
    from retrieved evidence.

    Environment variables:
        DEEPSEEK_API_KEY — your DeepSeek API key
        DEEPSEEK_MODEL — model identifier (default: deepseek-chat)
    """
    model_config = SettingsConfigDict(env_prefix="DEEPSEEK_")

    api_key: str = ""
    model: str = "deepseek-chat"


class CohereSettings(BaseSettings):
    """
    Cohere embedding provider settings.

    Used by the indexing module to convert text chunks into vector embeddings
    for similarity search.

    Environment variables:
        COHERE_API_KEY — your Cohere API key
        COHERE_EMBED_MODEL — embedding model (default: embed-english-v3.0)
    """
    model_config = SettingsConfigDict(env_prefix="COHERE_")

    api_key: str = ""
    embed_model: str = "embed-english-v3.0"


# ─────────────────────────────────────────────────────────────────────────────
# Combined Settings
# ─────────────────────────────────────────────────────────────────────────────


class Settings:
    """
    Top-level settings container that composes all settings groups.

    This is the single object the rest of the application uses.
    Each group is created as an attribute, so you access config like:
        settings.app.port
        settings.database.url
        settings.auth.secret_key
        settings.deepseek.api_key
        settings.cohere.embed_model

    WHY not a single flat BaseSettings?
    Grouping keeps related settings together and avoids a giant class
    with 20+ fields. It also lets each group define its own env_prefix,
    so environment variables stay clean and namespaced.
    """

    def __init__(self):
        self.app = AppSettings()
        self.database = DatabaseSettings()
        self.auth = AuthSettings()
        self.deepseek = DeepSeekSettings()
        self.cohere = CohereSettings()


# ─────────────────────────────────────────────────────────────────────────────
# Cached Settings Loader
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application settings, cached after first call.

    WHY caching?
    Settings are read from environment variables, which don't change
    during the lifetime of a running process. Reading them once and
    caching the result avoids repeated parsing and validation work
    on every request.

    HOW lru_cache works:
    The @lru_cache decorator stores the return value of the first call.
    Every subsequent call returns the stored value without executing
    the function body again. maxsize=1 means we only cache one result
    (since we always call with no arguments).
    """
    return Settings()
