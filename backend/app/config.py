from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = f"sqlite:///{(DATA_DIR / 'jobs.db').as_posix()}"

    polza_api_key: str = ""
    polza_base_url: str = "https://polza.ai/api/v1/"
    llm_model_fast: str = "anthropic/claude-haiku-5.5"
    llm_model_smart: str = "anthropic/claude-sonnet-5.5"
    embedding_model: str = "baai/bge-m3"

    exa_api_key: str = ""

    default_region_code: str = "5900000000000"  # Пермский край


@lru_cache
def get_settings() -> Settings:
    return Settings()
