from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://argus:argus@localhost:5432/argus"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32)
    export_directory: str = "./exports"
    token_minutes: int = 480
    assignment_timeout_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]


@lru_cache
def settings():
    return Settings()
