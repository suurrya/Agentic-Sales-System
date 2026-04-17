"""
reset.py
========
Resets the PaperTrail Co. database to its initial state.

Run from the project root:

    python src/database/reset.py

What this does
--------------
  1. Drops and recreates the `transactions` table (clears all sales history)
  2. Reseeds the `inventory` table with full starting stock
  3. Reseeds `quote_requests` and `quotes` from the CSV input files
  4. Inserts the opening cash balance of $50,000
  5. Inserts one stock_orders row per inventory item

Stock levels after reset will match the values in generate_sample_inventory()
with seed=137, which is the same seed used by evaluator/evaluation.py.

Use this when:
  - Stock has been depleted by web requests and you want a fresh start
  - You want to re-run batch tests without running the full evaluation.py pipeline
  - The database is in an inconsistent state
"""

import os
import sys
import threading
from datetime import datetime

# Allow running from the project root OR from inside src/database/
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_here, "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd

from src.database.database import db_engine, init_database, generate_financial_report

OLTP_PATH = "data/output/oltp_database.csv"
OLAP_PATH = "data/output/olap_database.csv"

_csv_lock = threading.Lock()


def _append_row(path: str, row: dict) -> None:
    """Thread-safe CSV append — creates file with header if it doesn't exist yet."""
    with _csv_lock:
        df = pd.DataFrame([row])
        if os.path.exists(path) and os.path.getsize(path) > 0:
            df.to_csv(path, mode="a", header=False, index=False)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            df.to_csv(path, index=False)


def _get_current_stats(engine):
    """Read a snapshot of the DB before reset for the before/after summary."""
    try:
        txns = pd.read_sql("SELECT transaction_type, COUNT(*) as n FROM transactions GROUP BY transaction_type", engine)
        sales = int(txns.loc[txns["transaction_type"] == "sales", "n"].sum())
        orders = int(txns.loc[txns["transaction_type"] == "stock_orders", "n"].sum())
        cash = pd.read_sql(
            "SELECT COALESCE(SUM(CASE WHEN transaction_type='sales' THEN price ELSE -price END), 0) AS cash FROM transactions",
            engine,
        ).iloc[0]["cash"]
        return {"sales": sales, "stock_orders": orders, "cash": float(cash)}
    except Exception:
        return None


def main():
    print()
    print("=" * 55)
    print("  PaperTrail Co. — Database Reset")
    print("=" * 55)

    # ── Before snapshot ────────────────────────────────────────
    before = _get_current_stats(db_engine)
    if before:
        print(f"\n  Before reset:")
        print(f"    Sales transactions : {before['sales']}")
        print(f"    Stock orders       : {before['stock_orders']}")
        print(f"    Cash balance       : ${before['cash']:,.2f}")
    else:
        print("\n  No existing database found — creating fresh.")

    # ── Confirm ────────────────────────────────────────────────
    print()
    confirm = input("  Reset will wipe all sales history. Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("  Aborted — database unchanged.")
        print()
        return

    # ── Reset ──────────────────────────────────────────────────
    print("\n  Resetting...")
    init_database(db_engine)

    # ── After snapshot ─────────────────────────────────────────
    after = _get_current_stats(db_engine)
    inv = pd.read_sql("SELECT COUNT(*) as n, SUM(current_stock) as total_stock FROM inventory", db_engine)
    num_items = int(inv.iloc[0]["n"])
    total_stock = int(inv.iloc[0]["total_stock"])

    print()
    print("  After reset:")
    print(f"    Sales transactions : {after['sales']}")
    print(f"    Stock orders       : {after['stock_orders']}  (one per inventory item)")
    print(f"    Inventory items    : {num_items}")
    print(f"    Total units seeded : {total_stock:,}")
    print(f"    Opening cash       : ${after['cash']:,.2f}")

    # ── Append stock-replenishment event to OLTP and OLAP CSVs ─
    print("\n  Updating OLTP / OLAP logs...")
    ts = datetime.now().isoformat()
    reset_date = datetime.now().strftime("%Y-%m-%d")

    _append_row(OLTP_PATH, {
        "transaction_id": f"RESET_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "request_id": "SYSTEM",
        "timestamp": ts,
        "customer_type": "SYSTEM",
        "event": "Stock Reset",
        "is_fulfilled": True,
        "items_checked": num_items,
        "items_fulfilled": num_items,
        "total_value": 0.0,
    })

    report = generate_financial_report(db_engine, reset_date)
    _append_row(OLAP_PATH, {
        "request_id": "SYSTEM",
        "request_date": reset_date,
        "cash_balance": report["cash_balance"],
        "inventory_value": report["inventory_value"],
        "response": f"Stock reset — inventory restored to initial levels ({total_stock:,} units across {num_items} items)",
    })

    print(f"    OLTP event appended: Stock Reset ({num_items} items restocked)")
    print(f"    OLAP snapshot appended: cash ${report['cash_balance']:,.2f}, inventory ${report['inventory_value']:,.2f}")
    print()
    print("  Database reset complete.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
