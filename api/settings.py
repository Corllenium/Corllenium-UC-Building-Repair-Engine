from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIXER_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://fixer:fixer@127.0.0.1:5490/fixer"
    source_dir: Path = Path(r"D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17")
    data_dir: Path = Path("data")
    stable_interval_s: float = 1.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
