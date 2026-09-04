from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ai_platform"
    embedding_dimension: int = 3072

    github_token: str = ""
    openai_api_key: str = ""
    jwt_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
