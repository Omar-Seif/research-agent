from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and .env.

    Priority:
        1. Environment variables
        2. .env file
        3. Default values
    """

    # =========================================================================
    # LLM Configuration
    # =========================================================================

    GROQ_API_KEY: str
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    MODEL: str = "llama-3.1-8b-instant"

    # =========================================================================
    # Search Configuration
    # =========================================================================

    TAVILY_API_KEY: str
    MAX_SEARCH_RESULTS: int = 5
    # Domains Tavily is allowed to search.
    SEARCH_INCLUDE_DOMAINS: List[str] = []

    # =========================================================================
    # API Configuration
    # =========================================================================

    API_PREFIX: str = "/api"
    ALLOWED_ORIGINS: List[str] = []

    # =========================================================================
    # Application Configuration
    # =========================================================================

    DEBUG: bool = False

    # =========================================================================
    # Server Configuration
    # =========================================================================

    PORT: int = 8000

    # =========================================================================
    # Logging
    # =========================================================================

    LOG_LEVEL: str = "DEBUG"
    LOG_FILE_PATH: str = "logs/app.log"

    # =========================================================================
    # HTTP Client Configuration
    # =========================================================================

    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1

    # =============================================================================
    # Article Fetching Configuration
    # =============================================================================

    FETCH_TIMEOUT: int = 30  # Per-request timeout for article fetching
    MAX_CONTENT_BYTES: int = 10 * 1024 * 1024  # 10MB
    USER_AGENT: str = (
        "ResearchAgent/1.0 (+https://github.com/Omar-Seif/research-agent.git)"
    )

    # =========================================================================

    @field_validator("LOG_LEVEL", mode="after")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}, got: {v}")
        return upper_v

    @field_validator("SEARCH_INCLUDE_DOMAINS", mode="after")
    @classmethod
    def validate_search_include_domains(cls, domains: List[str]) -> List[str]:

        normalized: List[str] = []
        seen: set[str] = set()

        for domain in domains:
            domain = domain.strip().lower()

            if not domain:
                raise ValueError("SEARCH_INCLUDE_DOMAINS cannot contain empty values.")

            if domain not in seen:
                normalized.append(domain)
                seen.add(domain)

        return normalized

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
