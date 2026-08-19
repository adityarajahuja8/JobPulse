"""Typed application settings via pydantic-settings.

All values can be overridden via environment variables or a .env file.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    mongodb_url: str = Field(
        default="mongodb://localhost:27017/acdyon",
        description="MongoDB connection string.",
    )
    mongodb_db_name: str = Field(
        default="acdyon",
        description="MongoDB database name (extracted from URL by db.py).",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="structlog log level.")

    # ── Scheduler ─────────────────────────────────────────────────────────────
    run_interval_seconds: int = Field(
        default=300,
        description="Seconds between ingestion runs in watch mode.",
    )

    # ── Proxy (optional — blank = no proxy) ───────────────────────────────────
    proxy_url: str = Field(
        default="",
        description=(
            "Optional proxy URL for identity rotation. "
            "Format: http://user:pass@host:port or socks5://host:port. "
            "Leave blank for the demo — public APIs don't require it."
        ),
    )

    # ── Source toggles ────────────────────────────────────────────────────────
    remoteok_enabled: bool = Field(default=True, description="Enable RemoteOK adapter.")
    jsearch_enabled: bool = Field(default=True, description="Enable JSearch (RapidAPI) adapter.")
    arbeitnow_enabled: bool = Field(default=False, description="Enable Arbeitnow adapter (legacy).")

    # ── RapidAPI Credentials ─────────────────────────────────────────────────
    rapidapi_key: str = Field(
        default="e50277eb37msh360b11bca7c1866p1ca014jsn36fef6c35f06",
        description="RapidAPI Key for JSearch API.",
    )
    rapidapi_host: str = Field(
        default="jsearch.p.rapidapi.com",
        description="RapidAPI Host header for JSearch API.",
    )
    jsearch_query: str = Field(
        default="Software developer in USA",
        description="Search query parameter for JSearch.",
    )

    # ── HTTP client ───────────────────────────────────────────────────────────
    http_timeout_seconds: float = Field(
        default=30.0, description="Default HTTP request timeout."
    )
    http_max_retries: int = Field(
        default=3, description="Max retries per HTTP request before dead-lettering."
    )

    # ── Pacing defaults ───────────────────────────────────────────────────────
    # RemoteOK documents a 60-second crawl delay — mu must be >= 60 for that adapter.
    # General inter-request pacing uses a shorter mu suitable for any source.
    default_pacing_mu: float = Field(
        default=3.0, description="Log-normal mean delay (seconds) for general pacing."
    )
    default_pacing_sigma: float = Field(
        default=0.4, description="Log-normal sigma for general pacing."
    )
    global_throttle_seconds: float = Field(
        default=60.0, description="Global throttle delay (seconds) in fallback step 3."
    )


# Module-level singleton — import this everywhere instead of constructing repeatedly.
settings = Settings()
