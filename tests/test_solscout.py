import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from solscout.bot import run_once
from solscout.config import Settings
from solscout.dexscreener import DexScreener
from solscout.filters import build_candidates, passes
from solscout.store import AlertStore
from solscout.telegram import TelegramError, TelegramNotifier, format_alert

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
SETTINGS = Settings(dry_run=True, min_volume_h1=100_000, max_age_minutes=60)


def pair(token="MINT1", *, age_min=10, vol_h1=250_000, name="Pepe", liq=50_000, buys=300, sells=100):
    created = NOW - timedelta(minutes=age_min)
    return {
        "chainId": "solana",
        "dexId": "raydium",
        "url": f"https://dexscreener.com/solana/{token.lower()}",
        "pairAddress": f"PAIR-{token}-{age_min}",
        "baseToken": {"address": token, "name": name, "symbol": name.upper()},
        "quoteToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL"},
        "pairCreatedAt": int(created.timestamp() * 1000),
        "volume": {"h1": vol_h1, "h24": vol_h1 * 3},
        "liquidity": {"usd": liq} if liq is not None else None,
        "marketCap": 1_000_000,
        "txns": {"h1": {"buys": buys, "sells": sells}},
    }


def test_uses_h1_volume_not_h24():
    [c] = build_candidates([pair(vol_h1=40_000)], ["MINT1"], NOW)
    assert c.volume_h1 == 40_000
    assert not passes(c, SETTINGS)  # h24 would be 120k and wrongly pass


def test_age_comes_from_earliest_pair():
    # Old token with a brand-new pool must not look new.
    pairs = [pair(age_min=5, vol_h1=500_000), pair(age_min=600, vol_h1=1_000)]
    [c] = build_candidates(pairs, ["MINT1"], NOW)
    assert round(c.age_minutes) == 600
    assert c.volume_h1 == 500_000  # stats from the most active pair
    assert not passes(c, SETTINGS)


def test_ignores_pairs_where_token_is_quote_or_unrequested():
    p = pair(token="OTHER")
    assert build_candidates([p], ["MINT1"], NOW) == []


def test_missing_liquidity_is_allowed_by_default_and_filterable():
    [c] = build_candidates([pair(liq=None)], ["MINT1"], NOW)  # pump.fun bonding curve
    assert passes(c, SETTINGS)
    assert not passes(c, Settings(dry_run=True, min_liquidity_usd=10_000))


def test_buy_ratio_filter():
    [c] = build_candidates([pair(buys=10, sells=90)], ["MINT1"], NOW)
    assert passes(c, SETTINGS)
    assert not passes(c, Settings(dry_run=True, min_buy_ratio=0.5))


def test_alert_escapes_html_in_token_names():
    [c] = build_candidates([pair(name="<b>rug</b>&co")], ["MINT1"], NOW)
    text = format_alert(c)
    assert "<b>rug</b>" not in text
    assert "&lt;b&gt;rug&lt;/b&gt;&amp;co" in text
    assert "$250.0K" in text


def test_store_dedupes_by_address(tmp_path):
    store = AlertStore(str(tmp_path / "t.db"))
    assert not store.seen("MINT1")
    store.mark("MINT1")
    assert store.seen("MINT1")
    assert AlertStore(str(tmp_path / "t.db")).seen("MINT1")  # persists across restarts


# --- end-to-end with fake HTTP ------------------------------------------------


def fake_dexscreener(pairs):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/token-profiles") or path.startswith("/token-boosts"):
            feed = [{"chainId": "solana", "tokenAddress": p["baseToken"]["address"]} for p in pairs]
            feed.append({"chainId": "ethereum", "tokenAddress": "0xabc"})
            return httpx.Response(200, json=feed)
        if path.startswith("/tokens/v1/solana/"):
            wanted = set(path.rsplit("/", 1)[1].split(","))
            return httpx.Response(200, json=[p for p in pairs if p["baseToken"]["address"] in wanted])
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class Recorder:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, text):
        if self.fail:
            raise TelegramError("boom")
        self.sent.append(text)


def test_run_once_alerts_each_token_once(tmp_path):
    pairs = [pair("HOT", vol_h1=900_000), pair("COLD", vol_h1=5_000), pair("OLD", age_min=500)]
    store, notifier = AlertStore(str(tmp_path / "t.db")), Recorder()

    async def go():
        async with fake_dexscreener(pairs) as client:
            dex = DexScreener(client)
            first = await run_once(dex, store, notifier, SETTINGS, NOW)
            second = await run_once(dex, store, notifier, SETTINGS, NOW)
            return first, second

    assert asyncio.run(go()) == (1, 0)
    assert "HOT" in notifier.sent[0]


def test_failed_delivery_is_retried_next_cycle(tmp_path):
    store = AlertStore(str(tmp_path / "t.db"))

    async def go(notifier):
        async with fake_dexscreener([pair("HOT")]) as client:
            return await run_once(DexScreener(client), store, notifier, SETTINGS, NOW)

    assert asyncio.run(go(Recorder(fail=True))) == 0
    assert not store.seen("HOT")
    assert asyncio.run(go(Recorder())) == 1


def test_telegram_errors_never_leak_token():
    secret = "123456:SECRET-TOKEN"

    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TelegramNotifier(client, secret, "42").send("hi")

    with pytest.raises(TelegramError) as info:
        asyncio.run(go())
    assert "chat not found" in str(info.value)
    assert secret not in str(info.value)


def test_telegram_sends_html_payload():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TelegramNotifier(client, "t", "42").send("<b>x</b>")

    asyncio.run(go())
    assert seen == {
        "chat_id": "42",
        "text": "<b>x</b>",
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
