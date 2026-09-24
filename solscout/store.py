"""Remembers which tokens were already alerted, keyed by mint address."""

from __future__ import annotations

import sqlite3
import time


class AlertStore:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS alerted (token_address TEXT PRIMARY KEY, alerted_at REAL NOT NULL)"
        )
        self._db.commit()

    def seen(self, token_address: str) -> bool:
        row = self._db.execute("SELECT 1 FROM alerted WHERE token_address = ?", (token_address,)).fetchone()
        return row is not None

    def mark(self, token_address: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO alerted VALUES (?, ?)", (token_address, time.time()))
        self._db.commit()

    def prune(self, older_than_days: float = 7) -> int:
        """Drop old entries; a token that old can no longer pass the age filter anyway."""
        cutoff = time.time() - older_than_days * 86400
        cur = self._db.execute("DELETE FROM alerted WHERE alerted_at < ?", (cutoff,))
        self._db.commit()
        return cur.rowcount

    def close(self) -> None:
        self._db.close()
