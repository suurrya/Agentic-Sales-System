import pandas as pd
from datetime import datetime
from smolagents import tool
from src.database.database import db_engine, get_cash_balance, get_all_inventory


@tool
def get_item_unit_price(item_name: str) -> float:
    """
    Retrieves the unit price of an item from the inventory catalogue.
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
    """
    return get_all_inventory(db_engine, datetime.now().isoformat())


@tool
def get_current_cash_balance_tool() -> float:
    """
    Returns the current net cash balance (total sales revenue minus stock purchase costs).
    """
    return get_cash_balance(db_engine, datetime.now().isoformat())
