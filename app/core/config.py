"""Bootstrap settings loaded from the environment. Runtime config lives in the database."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_DIR: Path = Path("./data")
    DATABASE_URL: str = ""
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    TZ: str = "UTC"
    VAPID_SUBJECT: str = "https://github.com/grid-monitor/grid-monitor"

    @field_validator("DATA_DIR", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: object) -> Path:
        return Path(str(value)).expanduser()

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        db_path = (self.DATA_DIR / "gridmonitor.db").resolve()
        return f"sqlite+aiosqlite:///{db_path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
