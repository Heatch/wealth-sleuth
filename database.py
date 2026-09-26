"""
Database module for Portfolio Tracker.
Manages SQLite schema, connections, and basic CRUD helpers.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from config import DB_PATH

SCHEMA_SQL = """
-- Brokerages
CREATE TABLE IF NOT EXISTS brokerages (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Accounts (within brokerages)
-- Each (brokerage, account_type, currency) is a separate account.
-- Disnat has CAD + USD sub-accounts for both TFSA and non-reg (4 total).
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    brokerage_id INTEGER NOT NULL REFERENCES brokerages(id),
    account_type TEXT NOT NULL,
    account_identifier TEXT,
    currency TEXT NOT NULL DEFAULT 'CAD',
    UNIQUE(brokerage_id, account_type, currency)
);

-- Securities / company info
-- NOTE: symbol normalization is dynamic (see consolidate.normalize_symbol),
-- so no symbol_map table is needed.
CREATE TABLE IF NOT EXISTS securities (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT,
    currency TEXT NOT NULL,
    asset_class TEXT,
    is_cdr INTEGER DEFAULT 0,
    exchange TEXT,
    is_cash INTEGER DEFAULT 0,
    sector TEXT,
    industry TEXT,
    description TEXT,
    market_cap REAL,
    last_price REAL,
    last_price_date TEXT,
    trailing_pe REAL,
    forward_pe REAL,
    dividend_yield REAL,
    dividend_rate REAL,
    fifty_two_week_high REAL,
    fifty_two_week_low REAL
);

-- Transactions
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    security_id INTEGER REFERENCES securities(id),
    date TEXT NOT NULL,
    settlement_date TEXT,
    type TEXT NOT NULL,
    quantity REAL,
    price REAL,
    commission REAL DEFAULT 0,
    net_amount REAL NOT NULL,
    currency TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_txn_security ON transactions(security_id);
CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(date);

-- Holdings (materialized, refreshed from transactions)
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    security_id INTEGER NOT NULL REFERENCES securities(id),
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    total_cost_basis REAL NOT NULL,
    first_purchase_date TEXT,
    last_transaction_date TEXT,
    UNIQUE(account_id, security_id)
);

-- Historical daily close prices per security (populated by fetch_price_history.py)
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY,
    security_id INTEGER NOT NULL REFERENCES securities(id),
    date TEXT NOT NULL,
    close_price REAL NOT NULL,
    currency TEXT NOT NULL,
    UNIQUE(security_id, date)
);
CREATE INDEX IF NOT EXISTS idx_price_history_security_date
    ON price_history(security_id, date);

-- Historical USD->CAD FX rates (populated by fetch_price_history.py)
CREATE TABLE IF NOT EXISTS fx_history (
    date TEXT PRIMARY KEY,
    rate REAL NOT NULL
);

-- Manifest of processed transaction files (for change detection)
CREATE TABLE IF NOT EXISTS file_manifest (
    file_path TEXT PRIMARY KEY,
    file_size INTEGER,
    last_modified REAL,
    processed_at TEXT DEFAULT (datetime('now'))
);

-- Schema metadata
CREATE TABLE IF NOT EXISTS schema_metadata (
    version TEXT PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);
"""


def get_connection(db_path: Optional[Path] = None, timeout: float = 10.0) -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled.

    WAL mode allows concurrent readers alongside the background price
    fetcher thread. busy_timeout makes readers wait on locks instead of
    raising SQLITE_BUSY immediately (which surfaced as API 500s when the
    frontend fires 5 simultaneous queries during a background write).
    """
    path = db_path or DB_PATH
    # check_same_thread=False: FastAPI runs sync dependencies/endpoints on
    # different anyio worker threads per await point, so a per-request
    # connection may be touched from multiple threads over its lifetime.
    # This is safe because each request owns its connection exclusively;
    # nothing shares one connection concurrently across threads.
    conn = sqlite3.connect(path, timeout=timeout, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    # Concurrent readers + one writer; wait on locks instead of failing
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the database schema."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def set_schema_version(version: str, db_path: Optional[Path] = None) -> None:
    """Record the current schema version."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM schema_metadata")
        conn.execute(
            "INSERT INTO schema_metadata (version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        conn.commit()
    finally:
        conn.close()


def get_schema_version(db_path: Optional[Path] = None) -> Optional[str]:
    """Get the current schema version, or None if not initialized."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT version FROM schema_metadata ORDER BY applied_at DESC LIMIT 1"
        ).fetchone()
        return row["version"] if row else None
    finally:
        conn.close()


# New securities columns added for yfinance data (schema 1.3.0).
# migrate_securities_schema() adds any missing columns idempotently.
SECURITIES_EXTRA_COLUMNS = {
    "trailing_pe": "REAL",
    "forward_pe": "REAL",
    "dividend_yield": "REAL",
    "dividend_rate": "REAL",
    "fifty_two_week_high": "REAL",
    "fifty_two_week_low": "REAL",
    "country": "TEXT",
}


def migrate_securities_schema(db_path: Optional[Path] = None) -> list[str]:
    """Add any missing yfinance columns to securities. Returns added columns."""
    conn = get_connection(db_path)
    try:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(securities)").fetchall()
        }
        added = []
        for column, coltype in SECURITIES_EXTRA_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE securities ADD COLUMN {column} {coltype}")
                added.append(column)
        conn.commit()
        return added
    finally:
        conn.close()


def get_or_create_brokerage(
    conn: sqlite3.Connection, name: str
) -> int:
    """Get existing brokerage id or create new one."""
    row = conn.execute(
        "SELECT id FROM brokerages WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO brokerages (name) VALUES (?)", (name,)
    )
    return cursor.lastrowid


def get_or_create_account(
    conn: sqlite3.Connection,
    brokerage_id: int,
    account_type: str,
    currency: str = "CAD",
    account_identifier: Optional[str] = None,
) -> int:
    """Get existing account id or create new one.

    Accounts are keyed by (brokerage, account_type, currency) because
    brokerages like Disnat have separate CAD and USD sub-accounts.
    """
    row = conn.execute(
        "SELECT id FROM accounts WHERE brokerage_id = ? AND account_type = ? AND currency = ?",
        (brokerage_id, account_type, currency),
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO accounts (brokerage_id, account_type, currency, account_identifier) VALUES (?, ?, ?, ?)",
        (brokerage_id, account_type, currency, account_identifier),
    )
    return cursor.lastrowid


def migrate_accounts_schema(db_path: Optional[Path] = None) -> list[str]:
    """Add currency column to accounts if missing. Returns added columns."""
    conn = get_connection(db_path)
    try:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
        }
        added = []
        if "currency" not in existing:
            conn.execute("ALTER TABLE accounts ADD COLUMN currency TEXT NOT NULL DEFAULT 'CAD'")
            added.append("currency")
        conn.commit()
        return added
    finally:
        conn.close()


def get_or_create_security(
    conn: sqlite3.Connection,
    symbol: str,
    currency: str,
    name: Optional[str] = None,
    asset_class: Optional[str] = None,
    exchange: Optional[str] = None,
    is_cdr: int = 0,
    is_cash: int = 0,
) -> int:
    """Get existing security id or create new one."""
    row = conn.execute(
        "SELECT id FROM securities WHERE symbol = ?", (symbol,)
    ).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        """
        INSERT INTO securities (symbol, name, currency, asset_class, exchange, is_cdr, is_cash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (symbol, name, currency, asset_class, exchange, is_cdr, is_cash),
    )
    return cursor.lastrowid


def update_security_name(
    conn: sqlite3.Connection, security_id: int, candidate_name: str
) -> None:
    """Update a security's name if the candidate is shorter/cleaner.

    Used when multiple raw symbols normalize to the same canonical
    symbol (e.g., DLR and DLR-C -> DLR): prefer the shortest name,
    which drops transfer/contribution artifacts like
    "GLB X US DOLL CURR-A ETF - TRSF 5MBWGB1/5MBWGA3".
    """
    if not candidate_name:
        return
    row = conn.execute(
        "SELECT name FROM securities WHERE id = ?", (security_id,)
    ).fetchone()
    if not row:
        return
    existing = row["name"] or ""
    if len(candidate_name) < len(existing):
        conn.execute(
            "UPDATE securities SET name = ? WHERE id = ?",
            (candidate_name, security_id),
        )


def transaction_exists(conn: sqlite3.Connection, transaction_id: str) -> bool:
    """Check if a transaction already exists in the database."""
    row = conn.execute(
        "SELECT 1 FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    return bool(row)


def insert_transaction(
    conn: sqlite3.Connection,
    transaction_id: str,
    account_id: int,
    security_id: Optional[int],
    date: str,
    settlement_date: Optional[str],
    txn_type: str,
    quantity: float,
    price: float,
    commission: float,
    net_amount: float,
    currency: str,
    description: str,
) -> None:
    """Insert a transaction into the database."""
    conn.execute(
        """
        INSERT OR IGNORE INTO transactions
        (id, account_id, security_id, date, settlement_date, type, quantity, price, commission, net_amount, currency, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            account_id,
            security_id,
            date,
            settlement_date,
            txn_type,
            quantity,
            price,
            commission,
            net_amount,
            currency,
            description,
        ),
    )


def get_transaction_count(conn: sqlite3.Connection) -> int:
    """Get total number of transactions."""
    row = conn.execute("SELECT COUNT(*) as cnt FROM transactions").fetchone()
    return row["cnt"]


def get_holding_count(conn: sqlite3.Connection) -> int:
    """Get total number of holdings."""
    row = conn.execute("SELECT COUNT(*) as cnt FROM holdings").fetchone()
    return row["cnt"]


def get_security_count(conn: sqlite3.Connection) -> int:
    """Get total number of securities."""
    row = conn.execute("SELECT COUNT(*) as cnt FROM securities").fetchone()
    return row["cnt"]
