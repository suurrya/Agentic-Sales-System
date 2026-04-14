"""
fulfillment_tools.py
====================
smolagents tools for order fulfillment and delivery timeline estimation.

Exposed tools:
    get_delivery_timeline_tool — estimates supplier delivery date from quantity
    fulfill_order_tool         — commits a confirmed sale to the database

Helper:
    get_supplier_delivery_date — internal delivery date calculator (not a tool)
"""

from datetime import datetime, timedelta

from smolagents import tool

from src.database.database import create_transaction, db_engine


def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """Estimates the supplier delivery date based on order size and a base date.

    Uses a tiered lead-time model:
        ≤ 10 units  → same day (0 days)
        ≤ 100 units → next day (1 day)
        ≤ 1000 units → 4 business days
        > 1000 units → 7 business days

    Args:
        input_date_str: ISO-format date string used as the calculation base.
                        If parsing fails, defaults to today's date.
        quantity: Number of units being ordered.

    Returns:
        Estimated delivery date as a "YYYY-MM-DD" string.
    """
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        input_date_dt = datetime.now()

    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7
    return (input_date_dt + timedelta(days=days)).strftime("%Y-%m-%d")


@tool
def get_delivery_timeline_tool(quantity: int) -> str:
    """
    Estimates the supplier delivery date based on the order quantity.
    Uses today as the base date and applies a tiered lead-time model:
    same day for ≤10 units, next day for ≤100, 4 days for ≤1000, 7 days for larger orders.
    Args:
        quantity (int): Number of units being ordered.
    """
    return get_supplier_delivery_date(datetime.now().isoformat(), quantity)


@tool
def fulfill_order_tool(item_name: str, quantity: int, price: float, date: str) -> int:
    """
    Records a confirmed sale transaction in the database and returns the transaction ID.
    Writes a "sales" type transaction row via create_transaction(), which decrements
    the effective stock level for the item as of the given date.
    Args:
        item_name (str): Name of the item sold.
        quantity (int): Number of units sold.
        price (float): Total sale price in USD.
        date (str): Transaction date in YYYY-MM-DD format.
    """
    return create_transaction(db_engine, item_name, "sales", quantity, price, date)
