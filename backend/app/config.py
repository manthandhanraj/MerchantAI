"""Application configuration.

All runtime configuration is read from environment variables (or a `.env`
file at the project root). Nothing secret is ever hard-coded here.

Import the shared instance rather than constructing your own:

    from backend.app.config import settings
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <project root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed view over the environment. Defaults keep the app runnable
    with no `.env` present, which is what CI and a fresh clone rely on."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- Application ----------
    app_name: str = "MerchantAI"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Stored as a raw string so the value is easy to set in .env; use
    # `cors_origin_list` to consume it.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- Data ----------
    sales_file: str = "data/raw/merchant_sales.csv"
    customers_file: str = "data/raw/merchant_customers_daily.csv"

    # ---------- LLM (activated in Stage 6) ----------
    llm_enabled: bool = False
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sales_path(self) -> Path:
        return PROJECT_ROOT / self.sales_file

    @property
    def customers_path(self) -> Path:
        return PROJECT_ROOT / self.customers_file


@lru_cache
def get_settings() -> Settings:
    """Cached so the `.env` file is parsed once per process."""
    return Settings()


settings = get_settings()
