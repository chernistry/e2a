# ==== APPLICATION SETTINGS CONFIGURATION ==== #

"""
Application settings configuration for Octup E²A.

This module provides centralized configuration management using Pydantic Settings
with environment variable loading and validation for all application components.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


# ==== MAIN SETTINGS CLASS ==== #


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Provides comprehensive configuration for database connections, AI services,
    observability, authentication, and operational parameters with validation
    and type safety.
    """
    
    model_config = SettingsConfigDict(
        env_file='.env', 
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )
    
    # --► CORE APPLICATION SETTINGS
    APP_ENV: str = "dev"
    SERVICE_NAME: str = "octup-e2a"
    LOG_LEVEL: str = "INFO"
    
    # --► DATABASE CONFIGURATION (SUPABASE)
    DATABASE_URL: str
    DIRECT_URL: str | None = None
    
    # --► SUPABASE API CONFIGURATION
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None
    
    # --► REDIS CONFIGURATION (CLOUD OR LOCAL)
    REDIS_URL: str
    
    # --► AUTHENTICATION SETTINGS
    JWT_SECRET: str = "change-me-please-and-keep-long-random"
    
    # --► TENANT CONFIGURATION
    X_TENANT_ID: str = "demo-3pl"
    
    # --► AI SERVICE CONFIGURATION
    AI_PROVIDER_BASE_URL: str = "https://openrouter.ai/api/v1"
    AI_MODEL: str = "google/gemini-2.0-flash-exp:free"
    AI_API_KEY: str | None = None
    AI_MAX_DAILY_TOKENS: int = 200_000
    AI_MIN_CONFIDENCE: float = 0.55
    AI_TIMEOUT_SECONDS: int = 3
    AI_RETRY_MAX_ATTEMPTS: int = 2
    AI_SAMPLING_SEVERITY: str = "important_only"
    AI_MODE: str = "smart"  # full|fallback|smart
    
    # --► OBSERVABILITY CONFIGURATION
    OBSERVABILITY_PROVIDER: str = "newrelic"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_EXPORTER_OTLP_HEADERS: str | None = None
    OTEL_SERVICE_NAME: str | None = None
    OTEL_RESOURCE_ATTRIBUTES: str | None = None
    NEW_RELIC_LICENSE_KEY: str | None = None
    SENTRY_DSN: str | None = None
    SENTRY_ENV: str = "dev"
    
    # --► ALTERNATIVE OBSERVABILITY PROVIDERS
    SIGNOZ_OTLP_ENDPOINT: str | None = None
    SIGNOZ_OTLP_HEADERS: str | None = None
    GIGAPIPE_OTLP_ENDPOINT: str | None = None
    GIGAPIPE_OTLP_HEADERS: str | None = None
    
    # --► PREFECT WORKFLOW ORCHESTRATION
    PREFECT_API_URL: str = "http://localhost:4200/api"
    PREFECT_WORK_POOL: str = "default-agent-pool"
    PREFECT_AGENT_QUEUE: str = "default"
    PREFECT_FLOW_NAME: str = "invoice_validate_nightly"
    PREFECT_DEPLOYMENT_NAME: str = "nightly"
    PREFECT_SCHEDULE_CRON: str = "0 1 * * *"
    
    # --► PREFECT CLOUD CONFIGURATION (OPTIONAL)
    PREFECT_API_KEY: str | None = None
    PREFECT_ACCOUNT_ID: str | None = None
    PREFECT_WORKSPACE_ID: str | None = None
    
    # --► DATASET CONFIGURATION
    KAGGLE_DATASET_SLUG: str = "/data/dataset"
    DATASET_EVENTS_DIR: str = "./data/events"
    
    # --► INVOICE FILE GENERATION
    GENERATE_INVOICE_FILES: bool = True
    INVOICE_FILES_PATH: str = "/app/data/invoices"
    
    # --► SECURITY LIMITS
    MAX_REQUEST_BODY_BYTES: int = 1_048_576
    
    # --► METRICS CONFIGURATION
    PROMETHEUS_SCRAPE_PATH: str = "/metrics"
    
    # --► SLACK INTEGRATION CONFIGURATION
    SLACK_BOT_TOKEN: str | None = None
    SLACK_BOT_USER_ID: str | None = None
    SLACK_SIGNING_SECRET: str | None = None
    SLACK_DEFAULT_CHANNEL: str | None = None
    SLACK_NOTIFICATION_ENABLED: bool = False


# ==== GLOBAL SETTINGS INSTANCE ==== #


# Global settings instance for application-wide access
settings = Settings()


def get_settings() -> Settings:
    """
    Get global settings instance.
    
    Returns:
        Settings: Global application settings instance
    """
    return settings
