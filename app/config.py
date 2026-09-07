from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Firmware Monitor"
    database_url: str = "sqlite:////data/firmware-monitor.db"
    secret_key: str = "change-me"
    encryption_key: str = ""
    check_interval_minutes: int = 360
    firmware_check_interval_hours: int = 24
    request_timeout_seconds: float = 15
    max_response_bytes: int = 2_000_000
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
