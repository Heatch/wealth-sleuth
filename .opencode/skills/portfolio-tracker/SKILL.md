# Portfolio Tracker - Agent Skill Guide

## Project Overview

The Portfolio Tracker is a personal wealth management tool that consolidates
transaction history from multiple brokerages into a single source of truth (SSOT).
The system is designed to provide a unified view of all investments across accounts
and brokerages, both current and historical.

## Current Phase: Transaction Consolidation

The first phase focuses on building a script (`consolidate.py`) that:

1. Reads transaction documents from multiple brokerages
2. Normalizes them into a unified schema
3. Outputs a single `portfolio.json` with deduplication

### Supported Brokerages

| Brokerage | Folder | File Format | Account Types |
|-----------|--------|-------------|---------------|
| Wealthsimple | `wealthsimple/` | CSV | TFSA, Non-reg |
| qtrade | `qtrade/` | HTML-table (.xls) | General |
| Disnat | `disnat/` | Excel (.xlsx) | TFSA, Non-reg |

### Running the Script

```bash
# Install dependencies
pip install -r requirements.txt

# Run consolidation
python consolidate.py

# With custom paths
python consolidate.py --documents-dir path/to/docs --output path/to/output.json
```

### Adding a New Brokerage

1. Add brokerage folder mapping in `config.py` -> `BROKERAGE_MAP`
2. Add account type mapping in `config.py` -> `ACCOUNT_TYPE_MAP`
3. Add type normalization map in `config.py` -> `TYPE_MAPS`
4. Create parser function in `consolidate.py` -> `parse_<brokerage>(filepath, account_type)`
5. Register parser in `PARSERS` dict

### File Discovery Logic

The script scans `transaction documents/` recursively:
- Top-level folder = brokerage name
- Subfolder = account type (tfsa, non reg, etc.)
- Files matched by extension (.csv, .xls, .xlsx)

Multiple files per account are supported (e.g., Disnat's History.xlsx, History (1).xlsx).
Deduplication ensures no duplicate transactions when files overlap.

## End Vision

The consolidation script is the foundation for a full portfolio dashboard that will:

1. **Current Holdings View**: Show all current positions across brokerages
2. **Returns Analysis**: Calculate gains/losses, dividends received, etc.
3. **Historical States**: Answer questions like "What did my portfolio look like on date X?"
4. **Asset Allocation**: Breakdown by sector, geography, asset class
5. **Tax Reporting**: Generate reports for tax purposes

## Data Flow

```
Source Documents (CSV/XLS/XLSX)
        │
        ▼
  consolidate.py
        │
        ▼
  portfolio.json (SSOT)
        │
        ▼
  Web App / API (future)
```

## Key Design Decisions

1. **Hash-based deduplication**: Each transaction gets a unique ID based on key fields.
   This allows incremental updates without duplicating data.

2. **raw_data field**: Each transaction preserves the original row data for debugging.
   This will be removed in a future schema version once the system is stable.

3. **Normalized types**: All brokerage-specific types map to a unified set:
   buy, sell, dividend, interest, tax, deposit, withdrawal, transfer, other

4. **Single output file**: All transactions go into one `portfolio.json` regardless
   of brokerage or account type.

## Common Tasks

### Check what transactions exist
```bash
python -c "import json; d=json.load(open('portfolio.json')); print(f'Total: {d[\"metadata\"][\"total_transactions\"]}'); print(f'Brokerages: {d[\"metadata\"][\"brokerages\"]}')"
```

### Re-run consolidation from scratch
```bash
rm portfolio.json
python consolidate.py
```

### Add new transaction documents
Simply add files to the appropriate folder structure and re-run:
```bash
python consolidate.py
```

The script will only add new transactions, keeping all existing ones.

## Troubleshooting

### "No parser for brokerage"
- Check that the brokerage folder name is in `BROKERAGE_MAP` in config.py

### "Unknown type"
- Add the raw type to the appropriate `TYPE_MAPS` entry in config.py

### Duplicate transactions
- Check the hash fields in `HASH_FIELDS` - ensure they uniquely identify transactions
- Verify quantity precision (rounded to 6 decimal places for hashing)

### Missing data
- Check the `raw_data` field in the transaction to see original values
- Verify the parser is reading the correct column names
