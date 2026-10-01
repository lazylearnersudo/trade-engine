from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["local", "deployed"] = "local"
    execution_mode: Literal["DUMMY", "DISABLED", "LIVE"] = "DUMMY"
    database_url: str = "postgresql://trade:trade@localhost:5432/trade"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    app_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:8000"
    approved_outbound_ip: str = ""
    verified_outbound_ip: str = ""
    deployment_ack: str = ""
    broker_credentials_file: str = ""
    schedule_grace_minutes: int = 5


settings = Settings()
