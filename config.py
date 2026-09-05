"""
Configuration for Portfolio Tracker.
Contains constants, type mappings, and database path.

Symbol normalization is handled dynamically in consolidate.py
(see normalize_symbol, detect_asset_class, clean_security_name).
"""

from pathlib import Path

# Schema version for future migrations
SCHEMA_VERSION = "1.2.0"

# Base directories
BASE_DIR = Path(__file__).parent
DOCUMENTS_DIR = BASE_DIR / "transaction documents"
DB_PATH = BASE_DIR / "portfolio.db"

# Brokerage folder name -> normalized identifier
BROKERAGE_MAP = {
    "wealthsimple": "wealthsimple",
    "qtrade": "qtrade",
    "disnat": "disnat",
}

# Account type folder name -> normalized identifier
ACCOUNT_TYPE_MAP = {
    "tfsa": "tfsa",
    "non reg": "non_reg",
    "non_reg": "non_reg",
    "rrsp": "rrsp",
    "resp": "resp",
    "fhsa": "fhsa",
    "margin": "margin",
}

# Fields used to generate the deduplication hash
HASH_FIELDS = [
    "brokerage",
    "account_type",
    "date",
    "symbol",
    "quantity",
    "price",
    "net_amount",
    "type",
]

# Quantity decimal places for hash rounding
QUANTITY_PRECISION = 6

# Type normalization maps per brokerage
# Key: raw type from source (uppercase for matching)
# Value: normalized type

WEALTHSIMPLE_TYPE_MAP = {
    "TRADE/BUY": "buy",
    "TRADE/SELL": "sell",
    "DIVIDEND": "dividend",
    "INTEREST": "interest",
    "TAX": "tax",
    "MONEYMOVEMENT/EFT_IN": "deposit",
    "MONEYMOVEMENT/EFT": "deposit",  # positive amounts are deposits
    "MONEYMOVEMENT/E_TRFIN": "deposit",
    "MONEYMOVEMENT/TRANSFER": "transfer",
    "MONEYMOVEMENT/TRANSFER_TF": "transfer",
    "CORPORATEACTION": "other",
    "LEGACYCORPORATEACTION": "other",
    "BONUSPAYMENT": "other",
}

QTRADE_TYPE_MAP = {
    "BUY": "buy",
    "SELL": "sell",
    "CASH RECEIPT": "deposit",
    "US CASH DIVIDEND": "dividend",
    "CDN CASH DIVIDEND": "dividend",
    "DIVIDEND": "dividend",
    "IRS WHT(TREATY)- POOL 2": "tax",
    "IRS WHT": "tax",
}

DISNAT_TYPE_MAP = {
    "BUY": "buy",
    "SELL": "sell",
    "DIVIDEND": "dividend",
    "TRUST DIVIDEND": "dividend",
    "WITHHOLDING TAX": "tax",
    "CONTRIBUTION": "deposit",
    "DEPOSIT REC'D VIA CAISSE": "deposit",
    "TRANSFER IN": "transfer",
    "TRANSFER OUT": "transfer",
    "INTERNAL TRANSFER": "transfer",
    "CANCELLATION": "other",
}

# Combined type maps by brokerage
TYPE_MAPS = {
    "wealthsimple": WEALTHSIMPLE_TYPE_MAP,
    "qtrade": QTRADE_TYPE_MAP,
    "disnat": DISNAT_TYPE_MAP,
}

# Default currency by brokerage (when not explicitly provided)
DEFAULT_CURRENCY = {
    "wealthsimple": "CAD",
    "qtrade": "CAD",
    "disnat": "CAD",
}

# Exchange for Canadian Depositary Receipts (detected by "CDR" in name)
CDR_EXCHANGE = "NEO"
