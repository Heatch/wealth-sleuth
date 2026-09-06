"""
Portfolio Tracker - Transaction Consolidation Script

Reads transaction documents from multiple brokerages, normalizes them
into a unified schema, and writes them to a SQLite database with
dynamic symbol normalization and deduplication.

Usage:
    python consolidate.py
    python consolidate.py --documents-dir path/to/docs --db path/to/portfolio.db
"""

import argparse
import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config import (
    ACCOUNT_TYPE_MAP,
    BROKERAGE_MAP,
    CDR_EXCHANGE,
    DB_PATH,
    DOCUMENTS_DIR,
    QUANTITY_PRECISION,
    TYPE_MAPS,
)
from database import (
    get_connection,
    get_or_create_account,
    get_or_create_brokerage,
    get_or_create_security,
    init_db,
    insert_transaction,
    set_schema_version,
    transaction_exists,
    update_security_name,
)
from refresh_holdings import refresh_holdings


@dataclass
class Transaction:
    """Unified transaction representation across all brokerages."""

    id: str
    brokerage: str
    account_type: str
    date: str
    settlement_date: str
    type: str
    symbol: str
    name: str
    quantity: float
    price: float
    commission: float
    net_amount: float
    currency: str
    description: str


def generate_id(txn: Transaction) -> str:
    """Generate a unique hash ID for a transaction based on key fields.

    settlement_date is included because Disnat nodate transactions
    (dividends, taxes) share identical date/symbol/quantity but differ
    in settlement date — omitting it caused silent deduplication.
    """
    quantity_rounded = round(txn.quantity, QUANTITY_PRECISION)
    hash_string = (
        f"{txn.brokerage}"
        f"{txn.account_type}"
        f"{txn.date}"
        f"{txn.settlement_date}"
        f"{txn.symbol}"
        f"{quantity_rounded}"
        f"{txn.price}"
        f"{txn.net_amount}"
        f"{txn.type}"
    )
    return hashlib.sha256(hash_string.encode()).hexdigest()[:16]


def normalize_type(brokerage: str, raw_type: str, raw_subtype: str = "") -> str:
    """Normalize brokerage-specific transaction types to unified types."""
    type_map = TYPE_MAPS.get(brokerage, {})
    if raw_subtype:
        combined = f"{raw_type}/{raw_subtype}".upper()
        if combined in type_map:
            return type_map[combined]
    normalized = raw_type.upper().strip()
    if normalized in type_map:
        return type_map[normalized]
    return "other"


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if pd.isna(value) or value == "" or value == "-":
        return default
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_str(value, default: str = "") -> str:
    """Safely convert a value to string."""
    if pd.isna(value):
        return default
    return str(value).strip()


def parse_date(value) -> str:
    """Parse various date formats to YYYY-MM-DD string."""
    if pd.isna(value) or value == "" or value == "-":
        return ""
    value_str = str(value).strip()
    for fmt in ["%Y-%m-%d", "%d-%b-%y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"]:
        try:
            return datetime.strptime(value_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return pd.Timestamp(value_str).strftime("%Y-%m-%d")
    except Exception:
        # Unparseable content (e.g. CSV footers like
        # As of 2026-08-27 22:21 GMT-04:00) -> treat as no date.
        return ""


def is_garbage_date_row(raw_value) -> bool:
    # True when a date field has content that is neither empty,
    # the '-' nodate marker, nor an actually parseable date
    # (e.g. source-file footer lines). Such rows must be skipped.
    if raw_value is None:
        return False
    try:
        if pd.isna(raw_value):
            return False
    except (TypeError, ValueError):
        pass
    s = str(raw_value).strip()
    if not s or s == "-":
        return False
    return not parse_date(raw_value)


def normalize_symbol(raw_symbol: str) -> str:
    """Normalize brokerage-specific symbol formats to a canonical symbol.

    Rules (applied dynamically, no lookup table):
    - Strip `.TO` suffix (Wealthsimple TSX): MDA.TO -> MDA
    - Strip `-U` suffix (Disnat USD): FN-U -> FN
    - Strip `-C` suffix (Disnat CAD): AEM-C -> AEM, DLR-C -> DLR

    Note: Wealthsimple's `CASH` ticker is the Global X High Interest
    Savings ETF, NOT actual cash. Actual cash balances use the
    `CASH-{currency}` placeholders (e.g., CASH-CAD), which never appear
    as raw symbols in source documents.
    """
    symbol = raw_symbol.strip()
    if symbol.endswith(".TO"):
        symbol = symbol[:-3]
    elif symbol.endswith("-U"):
        symbol = symbol[:-2]
    elif symbol.endswith("-C"):
        symbol = symbol[:-2]
    return symbol


def detect_asset_class(name: str) -> tuple[str, int]:
    """Detect the asset class from a security name.

    Returns (asset_class, is_cdr).
    """
    name_upper = name.upper()
    if "CDR" in name_upper:
        return ("cdr", 1)
    if "ETF" in name_upper or "TRUST" in name_upper:
        return ("etf", 0)
    return ("stock", 0)


def clean_security_name(name: str) -> str:
    """Remove transfer/contribution artifacts from a security name.

    Disnat embeds transfer descriptions in the security name for
    Nobert's Gambit journals, e.g.:
        "GLB X US DOLL CURR-A ETF - TRSF 5MBWGB1/5MBWGA3"
        -> "GLB X US DOLL CURR-A ETF"
    """
    for marker in (" - TRSF ", " - CONT ", " - CONTRIBUTION"):
        idx = name.upper().find(marker)
        if idx > 0:
            name = name[:idx]
    # Remove Disnat account identifiers (e.g., 5MBWGB1/5MBWGA3)
    name = re.sub(r"\s*5MB[A-Z0-9/]+\s*", "", name)
    return name.strip()


def is_valid_security_symbol(symbol: str) -> bool:
    """Return False for placeholders like '-' or empty strings.

    These come from cash-only rows (deposits, contributions) and must
    not create securities — those transactions stay security-less
    (security_id=NULL) so cash flow is still tracked via net_amount.
    """
    sym = symbol.strip()
    return bool(sym) and sym != "-"


def clean_raw_value(value):
    """Clean a value for safe handling (convert NaN/Inf to None)."""
    if pd.isna(value) or (isinstance(value, float) and math.isinf(value)):
        return None
    return value


def parse_wealthsimple(filepath: Path, account_type: str) -> list[Transaction]:
    """Parse Wealthsimple CSV export files."""
    transactions = []
    df = pd.read_csv(filepath)

    for _, row in df.iterrows():
        if is_garbage_date_row(row.get("effective_date")):
            continue
        activity_type = safe_str(row.get("activity_type"))
        activity_sub_type = safe_str(row.get("activity_sub_type"))

        raw_type = activity_type
        raw_subtype = activity_sub_type
        if activity_type == "MoneyMovement":
            net_cash = safe_float(row.get("net_cash_amount"))
            if net_cash < 0:
                raw_subtype = "WITHDRAWAL"
            else:
                raw_subtype = activity_sub_type

        normalized_type = normalize_type("wealthsimple", raw_type, raw_subtype)
        quantity = safe_float(row.get("quantity"))
        net_amount = safe_float(row.get("net_cash_amount"))

        if normalized_type in ("deposit", "withdrawal") and quantity == 0:
            quantity = abs(net_amount)

        txn = Transaction(
            id="",
            brokerage="wealthsimple",
            account_type=account_type,
            date=parse_date(row.get("effective_date")),
            settlement_date=parse_date(row.get("settlement_date")),
            type=normalized_type,
            symbol=safe_str(row.get("symbol")),
            name=safe_str(row.get("name")),
            quantity=quantity,
            price=safe_float(row.get("unit_price")),
            commission=safe_float(row.get("commission")),
            net_amount=net_amount,
            currency=safe_str(row.get("currency"), "CAD"),
            description=safe_str(row.get("description")),
        )
        txn.id = generate_id(txn)
        transactions.append(txn)

    return transactions


def parse_qtrade(filepath: Path, account_type: str) -> list[Transaction]:
    """Parse qtrade HTML-table .xls export files."""
    transactions = []
    dfs = pd.read_html(filepath)
    if not dfs:
        return transactions
    df = dfs[0]

    for _, row in df.iterrows():
        if is_garbage_date_row(row.get("Entry Date")):
            continue
        action = safe_str(row.get("Action"))
        normalized_type = normalize_type("qtrade", action)
        quantity = safe_float(row.get("Qty"))
        price = safe_float(row.get("Price"))
        net_amount = safe_float(row.get("Net Amount"))
        commission = safe_float(row.get("Comm."))

        if normalized_type == "deposit" and quantity == 0:
            quantity = abs(net_amount)

        txn = Transaction(
            id="",
            brokerage="qtrade",
            account_type=account_type,
            date=parse_date(row.get("Entry Date")),
            settlement_date=parse_date(row.get("Settlement Date")),
            type=normalized_type,
            symbol=safe_str(row.get("Symbol")),
            name=safe_str(row.get("Description")),
            quantity=quantity,
            price=price,
            commission=commission,
            net_amount=net_amount,
            currency="CAD",
            description=safe_str(row.get("Description")),
        )
        txn.id = generate_id(txn)
        transactions.append(txn)

    return transactions


def parse_disnat(filepath: Path, account_type: str) -> list[Transaction]:
    """Parse Disnat Excel export files."""
    transactions = []
    df = pd.read_excel(filepath)

    for _, row in df.iterrows():
        if is_garbage_date_row(row.get("Trade Date")):
            continue
        txn_type = safe_str(row.get("Transaction Type"))
        normalized_type = normalize_type("disnat", txn_type)
        quantity = safe_float(row.get("Quantity"))
        price = safe_float(row.get("Price"))
        net_amount = safe_float(row.get("Settlement Amount"))
        commission = safe_float(row.get("Commission Paid"))

        if normalized_type == "deposit" and quantity == 0:
            quantity = abs(net_amount)

        currency = safe_str(row.get("Price Currency"))
        if not currency or currency == "-":
            currency = safe_str(row.get("Account Currency"), "CAD")

        txn = Transaction(
            id="",
            brokerage="disnat",
            account_type=account_type,
            date=parse_date(row.get("Trade Date")),
            settlement_date=parse_date(row.get("Settlement Date")),
            type=normalized_type,
            symbol=safe_str(row.get("Symbol")),
            name=safe_str(row.get("Description")),
            quantity=quantity,
            price=price,
            commission=commission,
            net_amount=net_amount,
            currency=currency,
            description=safe_str(row.get("Description")),
        )
        txn.id = generate_id(txn)
        transactions.append(txn)

    return transactions


PARSERS = {
    "wealthsimple": parse_wealthsimple,
    "qtrade": parse_qtrade,
    "disnat": parse_disnat,
}


def discover_files(base_dir: Path) -> list[tuple[Path, str, str]]:
    """Discover all transaction files in the documents directory."""
    files = []
    if not base_dir.exists():
        print(f"Warning: Documents directory not found: {base_dir}")
        return files

    for brokerage_dir in base_dir.iterdir():
        if not brokerage_dir.is_dir():
            continue
        brokerage_name = brokerage_dir.name.lower()
        if brokerage_name not in BROKERAGE_MAP:
            print(f"Warning: Unknown brokerage folder: {brokerage_name}")
            continue
        brokerage = BROKERAGE_MAP[brokerage_name]

        for item in brokerage_dir.rglob("*"):
            if not item.is_file():
                continue
            account_type = "unknown"
            parent_name = item.parent.name.lower()
            if parent_name in ACCOUNT_TYPE_MAP:
                account_type = ACCOUNT_TYPE_MAP[parent_name]
            elif brokerage_dir == item.parent:
                account_type = "general"

            suffix = item.suffix.lower()
            if suffix in (".csv", ".xls", ".xlsx"):
                files.append((item, brokerage, account_type))

    return files


def consolidate(
    documents_dir: Path, db_path: Path, fetch_info: bool = False
) -> None:
    """Main consolidation function."""
    print(f"Scanning for transaction documents in: {documents_dir}")
    files = discover_files(documents_dir)
    print(f"Found {len(files)} transaction file(s)")

    if not files:
        print("No transaction files found. Exiting.")
        return

    # Parse all files
    all_transactions = []
    for filepath, brokerage, account_type in files:
        parser = PARSERS.get(brokerage)
        if not parser:
            print(f"Warning: No parser for brokerage '{brokerage}', skipping {filepath}")
            continue
        print(f"  Parsing: {filepath} ({brokerage}/{account_type})")
        try:
            transactions = parser(filepath, account_type)
            all_transactions.extend(transactions)
            print(f"    -> {len(transactions)} transactions")
        except Exception as e:
            print(f"    -> Error: {e}")

    print(f"\nTotal transactions parsed: {len(all_transactions)}")

    # Initialize database
    print(f"Initializing database: {db_path}")
    init_db(db_path)

    conn = get_connection(db_path)
    try:
        # Insert brokerages
        brokerage_ids = {}
        for brokerage in BROKERAGE_MAP.values():
            brokerage_ids[brokerage] = get_or_create_brokerage(conn, brokerage)

        # Insert accounts
        account_cache = {}
        for txn in all_transactions:
            key = (txn.brokerage, txn.account_type)
            if key not in account_cache:
                account_cache[key] = get_or_create_account(
                    conn,
                    brokerage_ids[txn.brokerage],
                    txn.account_type,
                )

        # Insert securities (dynamic: no lookup table)
        security_cache = {}
        for txn in all_transactions:
            raw_symbol = txn.symbol
            if not is_valid_security_symbol(raw_symbol):
                continue
            canonical_symbol = normalize_symbol(raw_symbol)
            key = (canonical_symbol, txn.currency)
            if key in security_cache:
                # Prefer the shortest/cleanest name across variants
                # (e.g., DLR-C's clean name over DLR's transfer-suffixed one)
                cleaned = clean_security_name(txn.name or canonical_symbol)
                update_security_name(conn, security_cache[key], cleaned)
                continue

            cleaned_name = clean_security_name(txn.name or canonical_symbol)
            # Note: Wealthsimple's CASH ticker is the Global X High Interest
            # Savings ETF, which detect_asset_class() correctly classifies
            # as "etf" from its name. Actual cash uses the CASH-{currency}
            # placeholders, created separately below with asset_class="cash".
            asset_class, is_cdr = detect_asset_class(cleaned_name)
            exchange = CDR_EXCHANGE if is_cdr else None
            is_cash = 0

            security_cache[key] = get_or_create_security(
                conn,
                canonical_symbol,
                txn.currency,
                name=cleaned_name,
                asset_class=asset_class,
                exchange=exchange,
                is_cdr=is_cdr,
                is_cash=is_cash,
            )

        # Ensure cash securities exist (before transactions so deposits resolve)
        for currency in ("CAD", "USD"):
            security_cache[(f"CASH-{currency}", currency)] = get_or_create_security(
                conn,
                f"CASH-{currency}",
                currency,
                name=f"Cash {currency}",
                asset_class="cash",
                is_cash=1,
            )

        # Insert transactions with deduplication
        added = 0
        skipped = 0
        for txn in all_transactions:
            if transaction_exists(conn, txn.id):
                skipped += 1
                continue

            account_id = account_cache[(txn.brokerage, txn.account_type)]
            security_id = None
            if is_valid_security_symbol(txn.symbol):
                canonical_symbol = normalize_symbol(txn.symbol)
                security_id = security_cache.get((canonical_symbol, txn.currency))
            elif txn.type in ("deposit", "withdrawal"):
                # Assign cash security for cash-only transactions
                cash_symbol = f"CASH-{txn.currency}"
                security_id = security_cache.get((cash_symbol, txn.currency))

            insert_transaction(
                conn,
                transaction_id=txn.id,
                account_id=account_id,
                security_id=security_id,
                date=txn.date,
                settlement_date=txn.settlement_date,
                txn_type=txn.type,
                quantity=txn.quantity,
                price=txn.price,
                commission=txn.commission,
                net_amount=txn.net_amount,
                currency=txn.currency,
                description=txn.description,
            )
            added += 1

        conn.commit()
        print(f"\nTransactions added: {added}")
        print(f"Transactions skipped (duplicates): {skipped}")

        # Refresh holdings
        print("Refreshing holdings...")
        result = refresh_holdings(db_path)
        print(f"  Cash holdings: {result['cash_holdings']}")
        print(f"  Security holdings: {result['security_holdings']}")

        # Set schema version
        from config import SCHEMA_VERSION
        set_schema_version(SCHEMA_VERSION, db_path)

    finally:
        conn.close()

    print(f"\nPortfolio database updated: {db_path}")

    if fetch_info:
        print("\nFetching security info from yfinance...")
        from fetch_security_info import update_securities

        info_result = update_securities(db_path=db_path)
        print(f"  Securities updated: {info_result['updated']}")
        print(f"  Failed: {info_result['failed']}")


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate transaction documents into the portfolio database."
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DOCUMENTS_DIR,
        help="Path to transaction documents directory",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--fetch-info",
        action="store_true",
        help="Also fetch security info from yfinance (off by default)",
    )

    args = parser.parse_args()
    consolidate(args.documents_dir, args.db, fetch_info=args.fetch_info)


if __name__ == "__main__":
    main()
