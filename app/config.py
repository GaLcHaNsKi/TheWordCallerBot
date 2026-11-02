from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import os

from dotenv import load_dotenv


def _time(name: str, default: str) -> time:
    try:
        return time.fromisoformat(os.getenv(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be HH:MM") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    default_timezone: str
    default_daily_time: time
    default_weekly_time: time
    bible_api_url: str
    bible_version: str
    log_level: str
    scheduler_interval_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "")
        if not token:
            raise ValueError("BOT_TOKEN is required")
        return cls(
            bot_token=token,
            mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
            mysql_user=os.getenv("MYSQL_USER", "bible_bot"),
            mysql_password=os.getenv("MYSQL_PASSWORD", ""),
            mysql_database=os.getenv("MYSQL_DATABASE", "bible_bot"),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
            default_daily_time=_time("DEFAULT_DAILY_TIME", "08:00"),
            default_weekly_time=_time("DEFAULT_WEEKLY_TIME", "21:00"),
            bible_api_url=os.getenv("BIBLE_API_URL", "https://api.midvash.com").rstrip("/"),
            bible_version=os.getenv("BIBLE_VERSION", "synodal"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            scheduler_interval_seconds=int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "45")),
        )
