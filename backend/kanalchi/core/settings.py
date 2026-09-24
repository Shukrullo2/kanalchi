"""Single source of configuration. Every process (api, workers, cli) reads the same env."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEV_SESSION_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../infra/.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- environment ---
    env: str = Field(default="dev", alias="APP_ENV")  # dev | prod
    log_level: str = "INFO"
    sentry_dsn: str | None = None

    # --- domains ---
    admin_host: str = "admin.localhost"
    # Channels onboarded without a domain of their own live under <slug>.<platform_domain>.
    # Unset, it is the admin host minus its first label: admin.example.uz gives example.uz.
    platform_domain: str | None = None
    public_ip: str | None = None
    public_scheme: str = "https"
    public_port: int | None = None  # dev: 8443 (Caddy); prod: None

    # --- secrets ---
    app_master_key: str | None = None
    app_master_key_prev: str | None = None
    session_secret: str = _DEV_SESSION_SECRET
    session_ttl_days: int = 30

    # --- telegram ---
    tg_api_id: int | None = None
    tg_api_hash: str | None = None
    platform_bot_token: str | None = None
    # NoDecode: the env value is a comma list (or empty), split by the validator below.
    # Without it an empty `ADMIN_TG_IDS=` is JSON-decoded first and startup fails.
    admin_tg_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # --- ai ---
    anthropic_api_key: str | None = None
    voyage_api_key: str | None = None
    chat_model: str = "claude-opus-5"
    extract_model: str = "claude-sonnet-5"
    # Consolidating candidate names into tags is list work, and unlike extraction its
    # output is reviewable: one proposal, a diff, applied by a human. Sonnet is a
    # reasonable default; set it to claude-opus-5 for a channel worth the extra.
    taxonomy_model: str = "claude-sonnet-5"
    # How often a name must appear before it is worth asking a model to canonicalise
    # it. At 1 the long tail of single mentions dominates: 39,000 candidates against
    # 2,200 at a floor of 5, for the same 72% of actual mentions.
    taxonomy_min_count: int = 5
    # Dimensions are independent of each other; chunks within one are not, because
    # each sees what earlier chunks proposed so they merge instead of duplicating.
    taxonomy_concurrency: int = 5
    embed_model: str = "voyage-4"
    embed_dim: int = 1024
    # Voyage throttles hard until the account has a payment method (3 requests and
    # 10k tokens a minute). Zero means "no client-side limit" — the normal case.
    embed_max_rpm: int = 0
    embed_max_tpm: int = 0
    # Posts per embedding job. Smaller means more frequent checkpoints, which
    # matters when a throttled account stretches one job over an hour.
    embed_job_posts: int = 500
    enable_refusal_fallbacks: bool = True

    # --- budgets / limits ---
    default_daily_chat_budget_usd: float = 5.0
    default_daily_studio_budget_usd: float = 20.0
    platform_daily_llm_cap_usd: float = 200.0
    media_max_bytes: int = 200 * 1024 * 1024
    # Media kinds never copied to storage: they keep a thumbnail and link to the post in
    # Telegram, as oversized files do. Comma list in the env, e.g. MEDIA_SKIP_KINDS=video.
    media_skip_kinds: Annotated[list[str], NoDecode] = Field(default_factory=list)
    viewer_chat_per_ip_10min: int = 10
    viewer_chat_per_visitor_day: int = 40
    viewer_chat_per_tenant_day: int = 300

    # --- datastores ---
    database_url: str = "postgresql+psycopg://kanalchi:kanalchi@localhost:5433/kanalchi"
    redis_url: str = "redis://localhost:6380/0"
    s3_endpoint: str = "http://localhost:9002"
    s3_access_key: str = "kanalchi"
    s3_secret_key: str = "kanalchi123"
    s3_region: str = "us-east-1"
    s3_bucket_media: str = "media"
    s3_bucket_uploads: str = "uploads"
    media_tmp_dir: str = "/var/tmp/media"

    @field_validator("admin_tg_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> list[int]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [int(x) for x in v.replace(";", ",").split(",") if x.strip()]
        return list(v)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def _prod_requires_real_secrets(self) -> Settings:
        if self.env != "prod":
            return self
        missing = []
        if not self.app_master_key:
            missing.append("APP_MASTER_KEY")
        if self.session_secret == _DEV_SESSION_SECRET or len(self.session_secret) < 32:
            missing.append("SESSION_SECRET (>= 32 random chars)")
        if missing:
            raise ValueError(
                "APP_ENV=prod but insecure configuration: set " + ", ".join(missing) + " (make gen-keys)"
            )
        return self

    @field_validator("media_skip_kinds", mode="before")
    @classmethod
    def _split_kinds(cls, v: object) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip().lower() for x in v.replace(";", ",").split(",") if x.strip()]
        return [str(x).lower() for x in v]  # type: ignore[union-attr]

    @property
    def is_dev(self) -> bool:
        return self.env != "prod"

    @property
    def tenant_base_domain(self) -> str:
        if self.platform_domain:
            return self.platform_domain.lower().strip(".")
        _, _, rest = self.admin_host.partition(".")
        return rest or self.admin_host

    @property
    def libpq_dsn(self) -> str:
        """DATABASE_URL without the SQLAlchemy driver suffix, for procrastinate / raw psycopg."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def public_url(self, host: str, path: str = "/") -> str:
        port = f":{self.public_port}" if self.public_port else ""
        return f"{self.public_scheme}://{host}{port}{path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
