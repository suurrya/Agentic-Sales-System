from datetime import datetime, timedelta
from smolagents import tool
from src.database.database import db_engine, create_transaction


def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """Estimates supplier delivery date based on order quantity."""
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity}")
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
    Args:
        quantity (int): Number of units being ordered.
    """
    return get_supplier_delivery_date(datetime.now().isoformat(), quantity)


@tool
def fulfill_order_tool(item_name: str, quantity: int, price: float, date: str) -> int:
    """
    Records a confirmed sale transaction in the database and returns the transaction ID.
    Args:
        item_name (str): Name of the item sold.
        quantity (int): Number of units sold.
        price (float): Total sale price.
        date (str): Transaction date in YYYY-MM-DD format.
    """
    return create_transaction(db_engine, item_name, "sales", quantity, price, date)
