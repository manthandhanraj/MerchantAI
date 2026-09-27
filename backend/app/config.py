"""Application configuration.

All runtime configuration is read from environment variables (or a `.env`
file at the project root). Nothing secret is ever hard-coded here.

Import the shared instance rather than constructing your own:

    from backend.app.config import settings
"""

import os
import uuid
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

    # ---------- Supabase (private multi-user workspace) ----------
    # Empty by default so the public demo still runs with no Supabase project.
    # `supabase_configured` is what every private route checks.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # Server-side only. Never expose this to the browser; it bypasses RLS.
    supabase_service_role_key: str = ""
    # Legacy HS256 projects sign with this. Newer projects use asymmetric keys
    # and are verified through JWKS instead, so only one of the two is needed.
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    supabase_data_bucket: str = "merchant-data"
    supabase_reports_bucket: str = "merchant-reports"

    # The shared public demo account. Read-only: the backend refuses every
    # mutating call from this user so a visitor cannot damage it for the next
    # one. Empty means no demo account is configured.
    demo_user_id: str = ""
    demo_user_email: str = "demo@merchantai.app"
    # Public by design: shown on the login page, and it opens a seeded,
    # synthetic, read-only workspace and nothing else.
    demo_password: str = "merchant-demo-2026"

    # ---------- Accounts ----------
    # "auto"     -> Supabase when it is configured, otherwise built-in accounts.
    # "supabase" -> Supabase only; a missing project is reported as 503.
    # "local"    -> built-in accounts only, even if Supabase keys are present.
    auth_mode: str = "auto"

    # Built-in accounts keep their data here: a SQLite database and the
    # uploaded files and reports. Empty means the default location.
    local_data_dir: str = ""
    # Signs built-in access tokens. Generated and stored inside
    # `local_data_dir` on first use when left empty, so a fresh checkout works;
    # set it explicitly when more than one server process must accept the
    # same tokens.
    local_auth_secret: str = ""
    local_token_ttl_hours: int = 168
    # Login attempts allowed per email inside the window before a pause.
    login_attempt_limit: int = 8
    login_attempt_window_seconds: int = 900

    # Limits applied to untrusted uploads before anything is parsed.
    max_upload_bytes: int = 10 * 1024 * 1024
    max_upload_rows: int = 200_000
    max_question_length: int = 500
    signed_url_ttl_seconds: int = 300

    # ---------- LLM (activated in Stage 6) ----------
    llm_enabled: bool = False
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: str = ""

    @property
    def supabase_configured(self) -> bool:
        """True when the private workspace can actually be served.

        The public demo does not depend on any of this, so a deployment with no
        Supabase project keeps working and the private routes return a clear
        503 instead of failing somewhere deeper.
        """
        return bool(self.supabase_url and self.supabase_anon_key)

    def is_demo_user(self, user_id: str) -> bool:
        """True when this caller is the shared demo account.

        Compared against an id rather than an email, because an email can be
        changed by the account holder and an id cannot. With built-in accounts
        the demo has a fixed id, so no configuration is needed.
        """
        if not user_id:
            return False
        if self.demo_user_id and user_id == self.demo_user_id:
            return True
        return self.resolved_auth_mode == "local" and user_id == LOCAL_DEMO_USER_ID

    @property
    def resolved_auth_mode(self) -> str:
        """Which account system this process is actually using."""
        mode = (self.auth_mode or "auto").strip().lower()
        if mode in ("local", "supabase"):
            return mode
        return "supabase" if self.supabase_configured else "local"

    @property
    def local_data_path(self) -> Path:
        if self.local_data_dir:
            return Path(self.local_data_dir)
        # Serverless platforms only allow writes under /tmp, and nothing
        # written there outlives the instance. See `local_storage_persistent`.
        if os.environ.get("VERCEL"):
            return Path("/tmp/merchantai-local")
        return PROJECT_ROOT / "data" / "local"

    @property
    def local_storage_persistent(self) -> bool:
        """False where built-in account data will not survive a restart."""
        return not (os.environ.get("VERCEL") and not self.local_data_dir)

    @property
    def supabase_rest_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/rest/v1"

    @property
    def supabase_storage_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/storage/v1"

    @property
    def supabase_auth_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sales_path(self) -> Path:
        return PROJECT_ROOT / self.sales_file

    @property
    def customers_path(self) -> Path:
        return PROJECT_ROOT / self.customers_file


# The built-in demo account's id. Fixed, so the backend can recognise the demo
# without any configuration and seeding stays idempotent across restarts.
LOCAL_DEMO_USER_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "merchantai:local-demo"))


@lru_cache
def get_settings() -> Settings:
    """Cached so the `.env` file is parsed once per process."""
    return Settings()


settings = get_settings()
