# SolScout

Telegram alerts for **new Solana tokens that are already trading hard**. It polls DexScreener every minute. When a token is under an hour old and has real volume, SolScout posts one alert to your chat and never alerts on that token again.

```
🚨 New Solana token: Rico Supreme ($RICO)
Age: 27 min · DEX: pumpswap
1h volume: $336.3K · Liquidity: $20.9K · MC: $61.4K
1h txns: 3830 buys / 2893 sells
26GZYEWdhxiP8wEzVyj9reBo59tL6wTkoYPJ2c4Cpump
View on DEX Screener
```

## How it works

1. **Discover.** Pull the latest Solana tokens from DexScreener's `token-profiles` and `token-boosts` feeds.
2. **Enrich.** Batch-look up every pair for those tokens (30 per request) through `/tokens/v1/solana/...`.
3. **Filter.** A token's age comes from its *earliest* pair, so an old token with a brand-new pool is not treated as new. Its volume, liquidity and buy/sell counts come from its busiest pair in the last hour.
4. **Alert once.** Tokens are deduplicated by mint address in a small SQLite file. A token is marked as alerted only after Telegram confirms delivery, so a failed send is retried on the next cycle.

## Quick start

```bash
git clone https://github.com/kjco0/SolScout && cd SolScout
python -m venv .venv && . .venv/bin/activate
pip install -e .
cp .env.example .env        # fill in TELEGRAM_TOKEN and CHAT_ID

DRY_RUN=1 python -m solscout   # print alerts to the terminal first
python -m solscout             # then send them to Telegram
```

## Configuration

Settings come from environment variables or `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_TOKEN` | – | Bot token from @BotFather |
| `CHAT_ID` | – | Chat or group to post to |
| `DRY_RUN` | `0` | `1` prints alerts instead of sending them |
| `MAX_AGE_MINUTES` | `60` | Maximum age of the token's first pair |
| `MIN_VOLUME_H1` | `100000` | Minimum USD volume in the last hour |
| `MIN_LIQUIDITY_USD` | `0` | pump.fun bonding-curve tokens report no liquidity, and `0` keeps them |
| `MIN_BUY_RATIO` | `0` | Minimum buys / (buys + sells) in the last hour |
| `POLL_SECONDS` | `60` | Scan interval (minimum 10) |
| `DB_PATH` | `solscout.db` | Where alerted tokens are stored |

## Deploy

SolScout is a single long-running process with no web server. [`deploy/solscout.service`](deploy/solscout.service) is an example systemd unit. Any host that can keep one Python process alive will also work, such as a VPS, Fly.io or Railway.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
```

Tests use `httpx.MockTransport`, so they make no network calls.

*Not financial advice. Most new tokens go to zero, so treat alerts as leads, not signals.*
