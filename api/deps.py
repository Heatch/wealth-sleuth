"""Shared FastAPI dependencies."""

import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Generator, Optional

from config import DB_PATH
from database import get_connection


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with row factory. FastAPI dependency."""
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

