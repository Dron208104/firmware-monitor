from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Firmware Monitor"
    app_version: str = "1.0.0"
    database_url: str = "sqlite:////data/firmware-monitor.db"
    secret_key: str = ""
    encryption_key: str = ""
    check_interval_minutes: int = 360
    firmware_check_interval_hours: int = 24
    request_timeout_seconds: float = 15
    max_response_bytes: int = 2_000_000
    max_request_bytes: int = 1_048_576
    session_lifetime_hours: int = 12
    session_inactivity_minutes: int = 15
    session_cookie_secure: bool = False
    initial_admin_username: str = ""
    initial_admin_password: str = ""
    auth_disabled: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
