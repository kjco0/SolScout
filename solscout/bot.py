"""Polling loop: discover new tokens, filter, alert once per token."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Protocol

import httpx

from .config import Settings
from .dexscreener import DexScreener
from .filters import build_candidates, passes
from .store import AlertStore
from .telegram import ConsoleNotifier, TelegramError, TelegramNotifier, format_alert

log = logging.getLogger(__name__)


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


async def run_once(
    dex: DexScreener,
    store: AlertStore,
    notifier: Notifier,
    settings: Settings,
    now: datetime | None = None,
) -> int:
    """One scan. Returns the number of alerts sent."""
    tokens = [t for t in await dex.latest_token_addresses() if not store.seen(t)]
    if not tokens:
        return 0
    pairs = await dex.pairs_for_tokens(tokens)
    hits = [c for c in build_candidates(pairs, tokens, now) if passes(c, settings)]
    log.info("scanned %d new tokens, %d passed filters", len(tokens), len(hits))

    sent = 0
    for c in sorted(hits, key=lambda c: c.volume_h1, reverse=True):
        try:
            await notifier.send(format_alert(c))
        except TelegramError as exc:
            log.error("alert for %s not sent: %s", c.token_address, exc)
            continue
        store.mark(c.token_address)  # only after delivery, so failures are retried
        sent += 1
    return sent


async def run_forever(settings: Settings) -> None:
    store = AlertStore(settings.db_path)
    headers = {"User-Agent": "SolScout/2.0 (+https://github.com/kjco0/SolScout)"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        dex = DexScreener(client)
        notifier: Notifier = (
            ConsoleNotifier()
            if settings.dry_run
            else TelegramNotifier(client, settings.telegram_token, settings.chat_id)
        )
        log.info(
            "SolScout started (%s): age <= %.0f min, 1h volume >= $%.0f, poll every %.0fs",
            "dry run" if settings.dry_run else "telegram",
            settings.max_age_minutes,
            settings.min_volume_h1,
            settings.poll_seconds,
        )
        try:
            while True:
                try:
                    await run_once(dex, store, notifier, settings)
                    store.prune()
                except Exception:
                    log.exception("scan failed; retrying next cycle")
                await asyncio.sleep(settings.poll_seconds)
        finally:
            store.close()
