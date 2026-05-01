"""
Sentinel Configuration Management.

Uses Pydantic Settings to load and validate environment variables.
Groups settings into logical sections for clean access.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    """Configuration for AI model providers."""
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    # API Keys (Optional here so the app can start, but required for AI logic)
    deepseek_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    google_api_key: Optional[str] = None


class AppSettings(BaseSettings):
    """General application settings."""
    model_config = SettingsConfigDict(
        env_prefix="APP_", 
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    env: str = "development"
    debug: bool = True
    port: int = 8000


class Settings:
    """Main settings container for the project."""
    def __init__(self):
        self.ai = AISettings()
        self.app = AppSettings()


# Create a global settings instance (Singleton pattern)
settings = Settings()
