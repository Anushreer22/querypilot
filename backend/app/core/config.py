from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate root directory and potential .env locations
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Application Database Connection (app_rw role on querypilot_app)
    app_database_url: str = (
        "postgresql+psycopg://app_rw:querypilot_app_rw_pass@127.0.0.1:5436/querypilot_app"
    )

    # Sample Shop Database Connection (readonly_user role on sample_shop)
    shop_database_url: str = (
        "postgresql+psycopg://readonly_user:querypilot_readonly_pass@127.0.0.1:5436/sample_shop"
    )

    # Privileged Database Connection for sample_shop (migrations & seeding as postgres)
    shop_admin_database_url: str = (
        "postgresql+psycopg://postgres:querypilot_postgres_pass@127.0.0.1:5436/sample_shop"
    )

    # Benchmark Database Connections (Phase 6 - isolated copy database)
    bench_database_url: str = (
        "postgresql+psycopg://readonly_user:querypilot_readonly_pass@127.0.0.1:5436/sample_shop_bench"
    )
    bench_admin_database_url: str = (
        "postgresql+psycopg://postgres:querypilot_postgres_pass@127.0.0.1:5436/sample_shop_bench"
    )

    # Optimizer & Benchmark Controls (Phase 6)
    rate_limit_optimize_per_minute: int = 5
    benchmark_default_iterations: int = 7
    benchmark_max_iterations: int = 15
    benchmark_timeout_seconds: float = 60.0

    # CORS Allowed Origins
    cors_origins: str | list[str] = ["http://localhost:5173"]

    # LLM Settings
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 1500
    llm_temperature: float = 0.0

    # Ask Endpoint & Security Controls
    rate_limit_ask_per_minute: int = 10
    schema_cache_ttl_seconds: int = 300

    # Agent Loop Controls (Phase 5)
    agent_max_steps: int = 6
    agent_timeout_seconds: float = 60.0
    agent_send_row_preview: bool = True
    rate_limit_agent_per_minute: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=(
            str(ROOT_DIR / ".env"),
            str(BASE_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
