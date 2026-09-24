"""Alert formatting and delivery through the Telegram Bot API."""

from __future__ import annotations

import asyncio
from html import escape as _html_escape

import httpx

from .filters import Candidate


def escape(text: str, quote: bool = False) -> str:
    return _html_escape(text, quote=quote)


class TelegramError(RuntimeError):
    """Delivery failed. The message never contains the bot token."""


def _usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"${value / size:.1f}{unit}"
    return f"${value:,.0f}"


def format_alert(c: Candidate) -> str:
    # Token names are attacker-controlled, so everything user-visible is HTML-escaped.
    return (
        f"🚨 <b>New Solana token</b>: {escape(c.name)} (${escape(c.symbol)})\n"
        f"Age: {c.age_minutes:.0f} min · DEX: {escape(c.dex_id)}\n"
        f"1h volume: {_usd(c.volume_h1)} · Liquidity: {_usd(c.liquidity_usd)} · MC: {_usd(c.market_cap)}\n"
        f"1h txns: {c.buys_h1} buys / {c.sells_h1} sells\n"
        f"<code>{escape(c.token_address)}</code>\n"
        f'<a href="{escape(c.pair_url, quote=True)}">View on DEX Screener</a>'
    )


class TelegramNotifier:
    def __init__(self, client: httpx.AsyncClient, token: str, chat_id: str):
        self._client = client
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(2):
            try:
                resp = await self._client.post(self._url, json=payload)
            except httpx.HTTPError as exc:
                # str(exc) can include the request URL, which embeds the token.
                raise TelegramError(f"network error: {type(exc).__name__}") from None
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 429 and attempt == 0:
                await asyncio.sleep(float(body.get("parameters", {}).get("retry_after", 5)))
                continue
            if resp.status_code != 200 or not body.get("ok"):
                raise TelegramError(f"HTTP {resp.status_code}: {body.get('description', 'no description')}")
            return


class ConsoleNotifier:
    """Used with DRY_RUN=1: prints alerts instead of sending them."""

    async def send(self, text: str) -> None:
        print(text, end="\n\n", flush=True)
