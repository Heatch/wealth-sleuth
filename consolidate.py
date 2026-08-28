"""
Portfolio Tracker - Transaction Consolidation Script

Reads transaction documents from multiple brokerages, normalizes them
into a unified schema, and outputs a single portfolio.json with
deduplication logic that handles incremental updates.

Usage:
    python consolidate.py
    python consolidate.py --documents-dir path/to/docs --output path/to/output.json
"""

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config import (
    ACCOUNT_TYPE_MAP,
    BROKERAGE_MAP,
    DEFAULT_CURRENCY,
    DOCUMENTS_DIR,
    HASH_FIELDS,
    OUTPUT_FILE,
    QUANTITY_PRECISION,
    SCHEMA_VERSION,
    TYPE_MAPS,
)


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
    raw_data: dict = field(default_factory=dict)


def generate_id(txn: Transaction) -> str:
    """Generate a unique hash ID for a transaction based on key fields."""
    # Round quantity to avoid floating point precision issues
    quantity_rounded = round(txn.quantity, QUANTITY_PRECISION)

    # Build hash string from key fields
    hash_string = (
        f"{txn.brokerage}"
        f"{txn.account_type}"
        f"{txn.date}"
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

    # Try combined type/subtype first (e.g., "TRADE/BUY")
    if raw_subtype:
        combined = f"{raw_type}/{raw_subtype}".upper()
        if combined in type_map:
            return type_map[combined]

    # Try just the type
    normalized = raw_type.upper().strip()
    if normalized in type_map:
        return type_map[normalized]

    # Default to "other" for unrecognized types
    return "other"


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if pd.isna(value) or value == "" or value == "-":
        return default
    if isinstance(value, str):
        # Remove currency symbols and commas
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


def clean_raw_data(data: dict) -> dict:
    """Clean raw_data dict to remove NaN/Inf values that are not valid JSON."""
    cleaned = {}
    for k, v in data.items():
        if pd.isna(v) or (isinstance(v, float) and math.isinf(v)):
            cleaned[k] = None
        elif isinstance(v, dict):
            cleaned[k] = clean_raw_data(v)
        else:
            cleaned[k] = v
    return cleaned


def parse_date(value) -> str:
    """Parse various date formats to YYYY-MM-DD string."""
    if pd.isna(value) or value == "" or value == "-":
        return ""

    value_str = str(value).strip()

    # Try common formats
    for fmt in ["%Y-%m-%d", "%d-%b-%y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"]:
        try:
            return datetime.strptime(value_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try pandas timestamp
    try:
        return pd.Timestamp(value_str).strftime("%Y-%m-%d")
    except Exception:
        return value_str


def parse_wealthsimple(filepath: Path, account_type: str) -> list[Transaction]:
    """Parse Wealthsimple CSV export files."""
    transactions = []

    df = pd.read_csv(filepath)

    for _, row in df.iterrows():
        # Determine transaction type
        activity_type = safe_str(row.get("activity_type"))
        activity_sub_type = safe_str(row.get("activity_sub_type"))

        # For MoneyMovement, determine deposit vs withdrawal based on amount
        raw_type = activity_type
        raw_subtype = activity_sub_type
        if activity_type == "MoneyMovement":
            net_cash = safe_float(row.get("net_cash_amount"))
            if net_cash < 0:
                raw_type = "MoneyMovement"
                raw_subtype = "WITHDRAWAL"
            else:
                raw_type = "MoneyMovement"
                raw_subtype = activity_sub_type  # EFT, E_TRFIN, etc.

        normalized_type = normalize_type("wealthsimple", raw_type, raw_subtype)

        # Get quantity - for MoneyMovement without quantity, use net_cash_amount
        quantity = safe_float(row.get("quantity"))
        net_amount = safe_float(row.get("net_cash_amount"))

        # For deposits/withdrawals, quantity might be the amount
        if normalized_type in ("deposit", "withdrawal") and quantity == 0:
            quantity = abs(net_amount)

        txn = Transaction(
            id="",  # Will be set after creation
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
            raw_data=clean_raw_data(row.to_dict()),
        )
        txn.id = generate_id(txn)
        transactions.append(txn)

    return transactions


def parse_qtrade(filepath: Path, account_type: str) -> list[Transaction]:
    """Parse qtrade HTML-table .xls export files."""
    transactions = []

    # qtrade files are HTML tables saved as .xls
    dfs = pd.read_html(filepath)
    if not dfs:
        return transactions
    df = dfs[0]

    for _, row in df.iterrows():
        action = safe_str(row.get("Action"))
        normalized_type = normalize_type("qtrade", action)

        # Parse quantity - remove NaN for non-trade transactions
        quantity = safe_float(row.get("Qty"))

        # Parse price - remove $ sign
        price = safe_float(row.get("Price"))

        # Parse net amount - remove $ sign and commas
        net_amount = safe_float(row.get("Net Amount"))

        # For deposits, quantity might be 0 but net_amount has value
        if normalized_type == "deposit" and quantity == 0:
            quantity = abs(net_amount)

        # Parse commission
        commission = safe_float(row.get("Comm."))

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
            currency="CAD",  # qtrade assumed CAD
            description=safe_str(row.get("Description")),
            raw_data=clean_raw_data(row.to_dict()),
        )
        txn.id = generate_id(txn)
        transactions.append(txn)

    return transactions


def parse_disnat(filepath: Path, account_type: str) -> list[Transaction]:
    """Parse Disnat Excel export files."""
    transactions = []

    df = pd.read_excel(filepath)

    for _, row in df.iterrows():
        txn_type = safe_str(row.get("Transaction Type"))
        normalized_type = normalize_type("disnat", txn_type)

        quantity = safe_float(row.get("Quantity"))
        price = safe_float(row.get("Price"))
        net_amount = safe_float(row.get("Settlement Amount"))
        commission = safe_float(row.get("Commission Paid"))

        # For deposits/contributions, quantity might be 0
        if normalized_type == "deposit" and quantity == 0:
            quantity = abs(net_amount)

        # Get currency - prefer Price Currency, fallback to Account Currency
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
            raw_data=clean_raw_data(row.to_dict()),
        )
        txn.id = generate_id(txn)
        transactions.append(txn)

    return transactions


# Map brokerages to their parser functions
PARSERS = {
    "wealthsimple": parse_wealthsimple,
    "qtrade": parse_qtrade,
    "disnat": parse_disnat,
}


def discover_files(base_dir: Path) -> list[tuple[Path, str, str]]:
    """
    Discover all transaction files in the documents directory.
    Returns list of (filepath, brokerage, account_type) tuples.
    """
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

            # Determine account type from parent folder
            account_type = "unknown"
            parent_name = item.parent.name.lower()
            if parent_name in ACCOUNT_TYPE_MAP:
                account_type = ACCOUNT_TYPE_MAP[parent_name]
            elif brokerage_dir == item.parent:
                # File is directly in brokerage folder
                # Try to infer from filename or default
                account_type = "general"

            # Check file extension
            suffix = item.suffix.lower()
            if suffix in (".csv", ".xls", ".xlsx"):
                files.append((item, brokerage, account_type))

    return files


def load_existing(filepath: Path) -> dict:
    """Load existing portfolio.json or return empty structure."""
    if not filepath.exists():
        return {
            "metadata": {
                "schema_version": SCHEMA_VERSION,
                "last_updated": "",
                "total_transactions": 0,
                "brokerages": [],
            },
            "transactions": [],
        }

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


class NaNSafeEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts NaN/Inf to null."""

    def default(self, o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        return super().default(o)

    def encode(self, o):
        return super().encode(self._clean(o))

    def _clean(self, o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, dict):
            return {k: self._clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [self._clean(v) for v in o]
        return o


def merge_transactions(existing: dict, new_transactions: list[Transaction]) -> dict:
    """Merge new transactions into existing portfolio, avoiding duplicates."""
    # Build set of existing transaction IDs
    existing_ids = {txn["id"] for txn in existing.get("transactions", [])}

    # Add only new transactions
    added_count = 0
    for txn in new_transactions:
        if txn.id not in existing_ids:
            existing["transactions"].append(asdict(txn))
            existing_ids.add(txn.id)
            added_count += 1

    # Update metadata
    existing["metadata"]["last_updated"] = datetime.now().isoformat()
    existing["metadata"]["total_transactions"] = len(existing["transactions"])

    # Collect unique brokerages
    brokerages = sorted(set(txn["brokerage"] for txn in existing["transactions"]))
    existing["metadata"]["brokerages"] = brokerages

    return existing, added_count


def consolidate(documents_dir: Path, output_path: Path) -> None:
    """Main consolidation function."""
    print(f"Scanning for transaction documents in: {documents_dir}")

    # Discover all files
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

    # Load existing portfolio
    existing = load_existing(output_path)
    print(f"Existing transactions in portfolio: {existing['metadata']['total_transactions']}")

    # Merge
    merged, added_count = merge_transactions(existing, all_transactions)
    print(f"New transactions added: {added_count}")
    print(f"Total transactions now: {merged['metadata']['total_transactions']}")

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, cls=NaNSafeEncoder)

    print(f"\nPortfolio saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate transaction documents into a single portfolio JSON."
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DOCUMENTS_DIR,
        help="Path to transaction documents directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="Path to output portfolio.json",
    )

    args = parser.parse_args()
    consolidate(args.documents_dir, args.output)


if __name__ == "__main__":
    main()
