"""Shared FastAPI dependencies."""

import sqlite3
from pathlib import Path
from typing import Generator, Optional

from config import DB_PATH
from database import get_connection

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a fresh SQLite connection per request. FastAPI dependency.

    NOTE: a shared module-level connection was tried here but breaks
    under uvicorn's threaded workers (sqlite3 objects are bound to the
    creating thread). Per-request connections are ~1ms and always safe.
    WAL + busy_timeout are set in get_connection() for concurrency.
    """
    conn = get_connection(None)
    try:
        yield conn
    finally:
        conn.close()


def get_db_path() -> Path:
    """Return the configured database path."""
    return DB_PATH


def validate_currency(currency: str) -> str:
    """Normalize and validate the display currency param."""
    c = (currency or "CAD").upper()
    if c not in ("CAD", "USD"):
        raise ValueError("currency must be CAD or USD")
    return c


def validate_period(period: str) -> str:
    """Normalize and validate the chart period param."""
    p = (period or "1y").lower()
    valid = {"1m", "6m", "ytd", "1y", "3y", "all"}
    if p not in valid:
        raise ValueError("period must be one of: 1m, 6m, ytd, 1y, 3y, all")
    return p


def parse_account_ids(accounts: Optional[str]) -> Optional[list[int]]:
    """Parse comma-separated account IDs. None/empty means all accounts."""
    if not accounts:
        return None
    try:
        ids = [int(x.strip()) for x in accounts.split(",") if x.strip()]
    except ValueError:
        raise ValueError("accounts must be comma-separated integer IDs")
    return ids or None

