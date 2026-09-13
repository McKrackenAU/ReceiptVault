from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RECEIPTVAULT_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    public_url: str = "http://127.0.0.1:8473"
    api_host: str = "127.0.0.1"
    api_port: int = 8473
    timezone: str = "Australia/Melbourne"
    log_level: str = "INFO"
    master_key: str = "dev-only-change-me-use-token-urlsafe-48bytes!!"
    session_seconds: int = 43200
    cookie_secure: bool = False
    trusted_proxies: str = ""
    database_url: str = "postgresql+psycopg://receiptvault:receiptvault_dev@127.0.0.1:5432/receiptvault"
    redis_url: str = "redis://127.0.0.1:6379/0"
    evidence_root: Path = Path("./var/evidence")
    derived_root: Path = Path("./var/derived")
    staging_root: Path = Path("./var/staging")
    backup_root: Path = Path("./var/backups")
    soft_delete_days: int = 30
    chunk_size_mib: int = 16
    max_upload_mib: int = 4096
    transfer_session_hours: int = 24
    package_expiry_hours: int = 48
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_tenant: str = "common"
    ms_redirect_path: str = "/api/v1/mail/oauth/callback"
    graph_mock: bool = False
    ai_enabled: bool = False
    ai_provider: str = ""
    ai_endpoint: str = ""
    ai_model: str = ""
    telemetry_opt_in: bool = False
    login_rate_per_minute: int = 8
    incremental_scan_minutes: int = 15
    cookie_name: str = "rv_session"
    csrf_header: str = "X-CSRF-Token"
    app_version: str = "1.5.1"

    @field_validator("chunk_size_mib")
    @classmethod
    def _chunk_bounds(cls, value: int) -> int:
        if value < 5 or value > 50:
            raise ValueError("chunk_size_mib must be between 5 and 50")
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxies.split(",") if item.strip()]

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.public_url.rstrip('/')}{self.ms_redirect_path}"

    @property
    def chunk_size_bytes(self) -> int:
        return self.chunk_size_mib * 1024 * 1024

    def ensure_dirs(self) -> None:
        for path in (self.evidence_root, self.derived_root, self.staging_root, self.backup_root):
            path.mkdir(parents=True, exist_ok=True)


def env_file_path() -> Path:
    explicit = os.environ.get("RECEIPTVAULT_ENV_FILE", "").strip()
    if explicit:
        return Path(explicit)
    for candidate in (Path("/etc/receiptvault/receiptvault.env"), Path("/opt/receiptvault/.env")):
        if candidate.exists():
            return candidate
    return Path(".env")


def upsert_env_key(key: str, value: str) -> Path:
    path = env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    written = False
    out: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            out.append(f"{key}={value}")
            written = True
        else:
            out.append(line)
    if not written:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    os.environ[key] = value
    return path


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
