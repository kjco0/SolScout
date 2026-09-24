"""Minimal async client for the public DexScreener API.

Docs: https://docs.dexscreener.com/api/reference
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com"
CHAIN = "solana"

# Feeds of recently listed / promoted tokens across all chains (60 req/min each).
DISCOVERY_FEEDS = ("token-profiles/latest/v1", "token-boosts/latest/v1")

# /tokens/v1 accepts at most 30 comma-separated addresses per call (300 req/min).
TOKENS_BATCH = 30


class DexScreener:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def _get(self, path: str) -> Any:
        resp = await self._client.get(f"{BASE_URL}/{path}")
        resp.raise_for_status()
        return resp.json()

    async def latest_token_addresses(self) -> list[str]:
        """Solana token addresses from the discovery feeds, newest first, de-duplicated."""
        seen: dict[str, None] = {}
        for feed in DISCOVERY_FEEDS:
            try:
                items = await self._get(feed)
            except httpx.HTTPError as exc:
                log.warning("DexScreener feed %s failed: %s", feed, exc)
                continue
            for item in items or []:
                if item.get("chainId") == CHAIN and item.get("tokenAddress"):
                    seen.setdefault(item["tokenAddress"], None)
        return list(seen)

    async def pairs_for_tokens(self, addresses: list[str]) -> list[dict[str, Any]]:
        """All Solana pairs that trade any of the given tokens."""
        pairs: list[dict[str, Any]] = []
        for i in range(0, len(addresses), TOKENS_BATCH):
            chunk = addresses[i : i + TOKENS_BATCH]
            try:
                pairs.extend(await self._get(f"tokens/v1/{CHAIN}/{','.join(chunk)}") or [])
            except httpx.HTTPError as exc:
                log.warning("DexScreener pair lookup failed for %d tokens: %s", len(chunk), exc)
        return pairs
