"""Runtime settings, read from environment variables (and a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_TRUTHY = {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw in (None, "") else float(raw)


@dataclass(frozen=True)
class Settings:
    telegram_token: str | None = None
    chat_id: str | None = None
    dry_run: bool = False

    poll_seconds: float = 60
    max_age_minutes: float = 60
    min_volume_h1: float = 100_000
    min_liquidity_usd: float = 0
    min_buy_ratio: float = 0.0

    db_path: str = "solscout.db"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        settings = cls(
            telegram_token=os.getenv("TELEGRAM_TOKEN") or None,
            chat_id=os.getenv("CHAT_ID") or None,
            dry_run=os.getenv("DRY_RUN", "").strip().lower() in _TRUTHY,
            poll_seconds=_float("POLL_SECONDS", cls.poll_seconds),
            max_age_minutes=_float("MAX_AGE_MINUTES", cls.max_age_minutes),
            min_volume_h1=_float("MIN_VOLUME_H1", cls.min_volume_h1),
            min_liquidity_usd=_float("MIN_LIQUIDITY_USD", cls.min_liquidity_usd),
            min_buy_ratio=_float("MIN_BUY_RATIO", cls.min_buy_ratio),
            db_path=os.getenv("DB_PATH") or cls.db_path,
        )
        if not settings.dry_run and not (settings.telegram_token and settings.chat_id):
            raise SystemExit(
                "TELEGRAM_TOKEN and CHAT_ID are required (or set DRY_RUN=1 to print alerts instead)."
            )
        if settings.poll_seconds < 10:
            raise SystemExit("POLL_SECONDS must be at least 10 to stay inside DexScreener rate limits.")
        return settings
