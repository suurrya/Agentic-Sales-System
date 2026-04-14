"""
pricing_tools.py
================
smolagents tools for retrieving item prices and financial snapshots.

Exposed tools:
    get_item_unit_price          — single-item price lookup from the inventory table
    get_full_inventory_report_tool — snapshot of all items and current stock levels
    get_current_cash_balance_tool  — net cash position (sales revenue minus purchase costs)
"""

from datetime import datetime

import pandas as pd
from smolagents import tool

from src.database.database import db_engine, get_all_inventory, get_cash_balance


@tool
def get_item_unit_price(item_name: str) -> float:
    """
    Retrieves the unit price of an item from the inventory catalogue.
    Returns 0.0 if the item is not found or a database error occurs,
    and prints the error for diagnostics.
    Args:
        item_name (str): The exact name of the inventory item.
    """
    try:
        price_df = pd.read_sql(
            "SELECT unit_price FROM inventory WHERE item_name = :item",
            db_engine,
            params={"item": item_name},
        )
        return float(price_df.iloc[0]["unit_price"]) if not price_df.empty else 0.0
    except Exception as e:
        print(f"Error fetching unit price for '{item_name}': {e}")
        return 0.0


@tool
def get_full_inventory_report_tool() -> dict:
    """
    Returns a dictionary of all inventory items and their current stock levels.
    Stock is calculated as of the current moment by summing all transactions
    up to now. Items with zero or negative net stock are excluded.
    """
    return get_all_inventory(db_engine, datetime.now().isoformat())


@tool
def get_current_cash_balance_tool() -> float:
    """
    Returns the current net cash balance (total sales revenue minus stock purchase costs).
    Includes the $50,000 opening cash injection recorded at database initialisation.
    """
    return get_cash_balance(db_engine, datetime.now().isoformat())
