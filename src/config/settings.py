from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and .env file.

    Values are loaded from (in order of priority):
    1. Environment variables (highest priority)
    2. .env file (local development)
    3. Default values (lowest priority)

    Required fields (no default):
        GROQ_API_KEY: Must be set in .env or environment

    Optional fields (with defaults):
        GROQ_BASE_URL, MODEL, API_PREFIX, DEBUG, LOG_LEVEL, ALLOWED_ORIGINS,
        REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY

    Usage:
        from src.config.settings import settings
        api_key = settings.GROQ_API_KEY
    """

    GROQ_API_KEY: str

    # API Configuration
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    MODEL: str = "llama-3.1-8b-instant"
    API_PREFIX: str = "/api"

    # Server Configuration
    DEBUG: bool = False
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE_PATH: str = "logs/app.log"

    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = []

    # API Behavior
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1

    @field_validator("LOG_LEVEL", mode="after")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}, got: {v}")
        return upper_v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
