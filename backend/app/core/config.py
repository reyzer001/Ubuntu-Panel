from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Ubuntu Panel API"
    app_version: str = "0.3.0"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 12
    database_url: str = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/ubuntu_panel"
    # "*" = izinkan akses dashboard dari host mana pun (localhost, LAN,
    # Tailscale). Autentikasi tetap lewat Bearer token, bukan cookie.
    cors_origins: list[str] = ["*"]
    admin_username: str = "admin"
    admin_password: str = "admin123"
    panel_agent_server: str = "http://192.168.11.126:8000"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
