"""Turn raw DexScreener pairs into per-token alert candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import Settings


@dataclass(frozen=True)
class Candidate:
    token_address: str
    name: str
    symbol: str
    pair_url: str
    dex_id: str
    age_minutes: float
    volume_h1: float
    liquidity_usd: float | None
    market_cap: float | None
    buys_h1: int
    sells_h1: int

    @property
    def buy_ratio(self) -> float:
        total = self.buys_h1 + self.sells_h1
        return self.buys_h1 / total if total else 0.0


def _h1_volume(pair: dict[str, Any]) -> float:
    return float((pair.get("volume") or {}).get("h1") or 0)


def build_candidates(
    pairs: Iterable[dict[str, Any]],
    tokens: Iterable[str],
    now: datetime | None = None,
) -> list[Candidate]:
    """One candidate per requested token.

    The token's age comes from its *earliest* pair, so an old token that just got a
    fresh pool does not look new. Stats come from its most active pair in the last hour.
    """
    now = now or datetime.now(timezone.utc)
    wanted = set(tokens)
    by_token: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        address = (pair.get("baseToken") or {}).get("address")
        if address in wanted and pair.get("pairCreatedAt"):
            by_token.setdefault(address, []).append(pair)

    candidates = []
    for address, token_pairs in by_token.items():
        first_created = min(p["pairCreatedAt"] for p in token_pairs)
        best = max(token_pairs, key=_h1_volume)
        created = datetime.fromtimestamp(first_created / 1000, tz=timezone.utc)
        txns = (best.get("txns") or {}).get("h1") or {}
        liquidity = (best.get("liquidity") or {}).get("usd")
        market_cap = best.get("marketCap") or best.get("fdv")
        candidates.append(
            Candidate(
                token_address=address,
                name=best["baseToken"].get("name") or "?",
                symbol=best["baseToken"].get("symbol") or "?",
                pair_url=best.get("url") or f"https://dexscreener.com/solana/{address}",
                dex_id=best.get("dexId") or "?",
                age_minutes=(now - created).total_seconds() / 60,
                volume_h1=_h1_volume(best),
                liquidity_usd=float(liquidity) if liquidity is not None else None,
                market_cap=float(market_cap) if market_cap is not None else None,
                buys_h1=int(txns.get("buys") or 0),
                sells_h1=int(txns.get("sells") or 0),
            )
        )
    return candidates


def passes(c: Candidate, s: Settings) -> bool:
    return (
        0 <= c.age_minutes <= s.max_age_minutes
        and c.volume_h1 >= s.min_volume_h1
        and (c.liquidity_usd or 0) >= s.min_liquidity_usd
        and c.buy_ratio >= s.min_buy_ratio
    )
