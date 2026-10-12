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

    # CORS Allowed Origins
    cors_origins: str | list[str] = ["http://localhost:5173"]

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
