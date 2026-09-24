import asyncio
import logging
import os

from .bot import run_forever
from .config import Settings


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO, and Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(run_forever(Settings.from_env()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
