# Portfolio Tracker - Code & Data Conventions

## Code Style

### Python Conventions
- **Type hints**: Use type hints for all function signatures and class attributes
- **Dataclasses**: Use `@dataclass` for structured data (e.g., `Transaction`)
- **Path handling**: Use `pathlib.Path` for all file paths
- **String formatting**: Use f-strings for string interpolation
- **Naming**: snake_case for variables, functions, and files

### Error Handling
- Use `safe_float()` and `safe_str()` helpers for data parsing
- Log warnings for unknown types/missing data, don't crash
- Use try/except for file operations with informative error messages

## Data Conventions

### Date Format
- All dates stored as `YYYY-MM-DD` strings
- Empty dates stored as empty string `""`
- Parse dates using `parse_date()` helper which handles multiple formats

### Numeric Values
- **Quantity**: Float, rounded to 6 decimal places for hashing
- **Price**: Float, as-is from source
- **Commission**: Float, 0 if not provided
- **Net Amount**: Float, negative for purchases, positive for sales/dividends

### Currency
- Always uppercase: `CAD`, `USD`
- qtrade assumed CAD (no currency field in source)
- Wealthsimple and Disnat have explicit currency fields

### Transaction Types
Normalized to these values:
- `buy` - Purchasing securities
- `sell` - Selling securities
- `dividend` - Dividend payments
- `interest` - Interest payments (stock lending, etc.)
- `tax` - Tax withholdings (IRS, non-resident, etc.)
- `deposit` - Money moving into the account
- `withdrawal` - Money moving out of the account
- `transfer` - Internal transfers between accounts
- `other` - Corporate actions, bonuses, etc.

### Symbol Handling
- Empty string `""` for transactions without symbols (deposits, transfers)
- Preserve original symbol format from source (e.g., `MDA.TO`, `DLR-C`, `FN-U`)
- Symbols are NOT normalized across brokerages (same stock may have different symbols)

### Account Types
Normalized to lowercase:
- `tfsa` - Tax-Free Savings Account
- `non_reg` - Non-registered account
- `rrsp` - Registered Retirement Savings Plan
- `resp` - Registered Education Savings Plan
- `fhsa` - First Home Savings Account
- `margin` - Margin account

## JSON Schema

### portfolio.json Structure
```json
{
  "metadata": {
    "schema_version": "1.0.0",
    "last_updated": "ISO-8601 timestamp",
    "total_transactions": 0,
    "brokerages": ["disnat", "qtrade", "wealthsimple"]
  },
  "transactions": [
    {
      "id": "16-char hex hash",
      "brokerage": "wealthsimple",
      "account_type": "tfsa",
      "date": "2025-01-03",
      "settlement_date": "2025-01-06",
      "type": "buy",
      "symbol": "CASH",
      "name": "Global X High Interest Savings ETF",
      "quantity": 40.0,
      "price": 50.02,
      "commission": 0.0,
      "net_amount": -2000.8,
      "currency": "CAD",
      "description": "Bought 40.0000 shares at $50.02 per share",
      "raw_data": {}
    }
  ]
}
```

### raw_data Field
- **Purpose**: Debugging and transparency
- **Content**: Original row data from source file as-is
- **Future**: Will be removed in schema version 2.0.0 once system is stable
- **Usage**: Use to trace transactions back to source data

## Deduplication

### Hash Generation
The transaction ID is a SHA-256 hash (truncated to 16 chars) of:
```
brokerage + account_type + date + symbol + quantity + price + net_amount + type
```

### Why These Fields?
- **brokerage + account_type**: Same transaction can't exist in two accounts
- **date**: When the transaction happened
- **symbol + quantity + price**: What was traded and at what price
- **net_amount**: Total cash impact
- **type**: buy vs sell vs dividend, etc.

### Edge Cases
- Quantity rounded to 6 decimal places before hashing
- Missing symbol = empty string
- Missing quantity = 0

## File Organization

```
Portfolio Tracker/
├── consolidate.py      # Main script
├── config.py           # Constants and mappings
├── requirements.txt    # Python dependencies
├── portfolio.json      # Output SSOT
├── SKILL.md            # Agent instructions
├── CONVENTIONS.md      # This file
└── transaction documents/
    ├── wealthsimple/
    │   ├── tfsa/
    │   └── non reg/
    ├── qtrade/
    └── disnat/
        ├── tfsa/
        └── non reg/
```

## Versioning

### Schema Version
- Follows semantic versioning: MAJOR.MINOR.PATCH
- MAJOR: Breaking changes to JSON structure
- MINOR: New fields added (backward compatible)
- PATCH: Bug fixes, no schema changes

Current version: `1.0.0`

### Migration Path
When schema changes are needed:
1. Update `SCHEMA_VERSION` in config.py
2. Add migration logic in consolidate.py if needed
3. Document changes in this file
