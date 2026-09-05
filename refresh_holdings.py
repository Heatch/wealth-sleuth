"""
Holdings refresh module for Portfolio Tracker.

Recomputes the materialized holdings table from transactions.

Algorithm:
1. Clear existing holdings
2. For each (account_id, security_id) pair:
   - Get all relevant transactions ordered by date
   - For securities: process buy/sell/transfer to compute quantity and avg cost
   - For cash (CASH-CAD, CASH-USD): sum net_amount across all transactions in that currency
3. Insert/update holdings
"""

import sqlite3
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection


def _get_cash_security_id(conn: sqlite3.Connection, currency: str) -> Optional[int]:
    """Get the security id for a cash placeholder symbol."""
    symbol = f"CASH-{currency}"
    row = conn.execute(
        "SELECT id FROM securities WHERE symbol = ?", (symbol,)
    ).fetchone()
    return row["id"] if row else None


def refresh_cash_holdings(conn: sqlite3.Connection) -> int:
    """Compute cash holdings from net_amount sums per account/currency."""
    # Get distinct account/currency combinations
    rows = conn.execute(
        """
        SELECT account_id, currency, SUM(net_amount) as balance
        FROM transactions
        GROUP BY account_id, currency
        HAVING balance != 0
        """
    ).fetchall()

    inserted = 0
    for row in rows:
        account_id = row["account_id"]
        currency = row["currency"]
        balance = row["balance"]

        security_id = _get_cash_security_id(conn, currency)
        if security_id is None:
            # Create cash security if it doesn't exist
            conn.execute(
                """
                INSERT INTO securities (symbol, name, currency, asset_class, is_cash)
                VALUES (?, ?, ?, 'cash', 1)
                """,
                (f"CASH-{currency}", f"Cash {currency}", currency),
            )
            security_id = conn.execute(
                "SELECT id FROM securities WHERE symbol = ?", (f"CASH-{currency}",)
            ).fetchone()["id"]

        # Get date range for this account's transactions in this currency
        date_range = conn.execute(
            """
            SELECT MIN(date) as first_date, MAX(date) as last_date
            FROM transactions
            WHERE account_id = ? AND currency = ?
            """,
            (account_id, currency),
        ).fetchone()

        conn.execute(
            """
            INSERT OR REPLACE INTO holdings
            (account_id, security_id, quantity, avg_cost, total_cost_basis, first_purchase_date, last_transaction_date)
            VALUES (?, ?, ?, 1.0, ?, ?, ?)
            """,
            (
                account_id,
                security_id,
                balance,
                balance,
                date_range["first_date"],
                date_range["last_date"],
            ),
        )
        inserted += 1

    return inserted


def refresh_security_holdings(conn: sqlite3.Connection) -> int:
    """Compute security holdings from buy/sell/transfer transactions."""
    # Get all non-cash securities with transactions
    rows = conn.execute(
        """
        SELECT DISTINCT t.account_id, t.security_id
        FROM transactions t
        JOIN securities s ON t.security_id = s.id
        WHERE (s.is_cash = 0 OR s.is_cash IS NULL)
          AND t.type IN ('buy', 'sell', 'transfer')
        """
    ).fetchall()

    inserted = 0
    for row in rows:
        account_id = row["account_id"]
        security_id = row["security_id"]

        # Get transactions in chronological order
        txns = conn.execute(
            """
            SELECT date, type, quantity, net_amount
            FROM transactions
            WHERE account_id = ? AND security_id = ? AND type IN ('buy', 'sell', 'transfer')
            ORDER BY date, id
            """,
            (account_id, security_id),
        ).fetchall()

        quantity = 0.0
        total_cost = 0.0
        avg_cost = 0.0
        first_date = None
        last_date = None

        for txn in txns:
            txn_type = txn["type"]
            txn_qty = txn["quantity"]
            txn_net = txn["net_amount"]
            txn_date = txn["date"]

            if first_date is None and txn_date:
                first_date = txn_date
            if txn_date:
                last_date = txn_date

            if txn_type == "buy":
                # Inflow: add quantity and cost
                qty_in = abs(txn_qty) if txn_qty else 0.0
                cost_in = abs(txn_net) if txn_net else 0.0
                quantity += qty_in
                total_cost += cost_in
                if quantity > 0:
                    avg_cost = total_cost / quantity

            elif txn_type == "transfer":
                # Transfers are signed: positive=in, negative=out.
                # Security transfers (e.g., Nobert's Gambit journals) have
                # net_amount=0; cash transfers have quantity=0.
                quantity += txn_qty if txn_qty else 0.0
                if txn_net:
                    total_cost += txn_net
                if quantity > 0:
                    avg_cost = total_cost / quantity
                else:
                    avg_cost = 0.0
                    total_cost = 0.0

            elif txn_type == "sell":
                # Outflow: reduce quantity and cost basis proportionally
                qty_out = abs(txn_qty) if txn_qty else 0.0
                if quantity > 0:
                    cost_reduction = avg_cost * qty_out
                    total_cost -= cost_reduction
                quantity -= qty_out
                if quantity > 0:
                    avg_cost = total_cost / quantity
                else:
                    avg_cost = 0.0
                    total_cost = 0.0

        if quantity != 0:
            conn.execute(
                """
                INSERT OR REPLACE INTO holdings
                (account_id, security_id, quantity, avg_cost, total_cost_basis, first_purchase_date, last_transaction_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    security_id,
                    quantity,
                    avg_cost,
                    total_cost,
                    first_date,
                    last_date,
                ),
            )
            inserted += 1

    return inserted


def refresh_holdings(db_path: Optional[Path] = None) -> dict:
    """Refresh all holdings from transactions."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM holdings")

        cash_count = refresh_cash_holdings(conn)
        security_count = refresh_security_holdings(conn)

        conn.commit()

        return {
            "cash_holdings": cash_count,
            "security_holdings": security_count,
            "total": cash_count + security_count,
        }
    finally:
        conn.close()


def main():
    """CLI entry point for refreshing holdings."""
    result = refresh_holdings()
    print(f"Refreshed holdings:")
    print(f"  Cash holdings: {result['cash_holdings']}")
    print(f"  Security holdings: {result['security_holdings']}")
    print(f"  Total: {result['total']}")


if __name__ == "__main__":
    main()
