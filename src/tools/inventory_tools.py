import re
import pandas as pd
from smolagents import tool
from src.database.database import db_engine, get_stock_level


@tool
def find_similar_inventory_item_tool(search_term: str) -> str:
    """
    Finds the best matching item name in the inventory catalogue using keyword overlap.
    Args:
        search_term (str): A description or partial name of the item to search for.
    """
    keywords = set(re.findall(r"\w+", search_term.lower()))
    if not keywords:
        return ""
    try:
        all_items = pd.read_sql("SELECT item_name FROM inventory", db_engine)
        if all_items.empty:
            return ""
        best_match, highest_score = None, 0
        for item_name in all_items["item_name"]:
            item_words = set(re.findall(r"\w+", item_name.lower()))
            score = len(keywords.intersection(item_words))
            if score > highest_score:
                highest_score, best_match = score, item_name
            elif score == highest_score and best_match and len(item_name) < len(best_match):
                best_match = item_name
        return best_match if highest_score > 0 else ""
    except Exception:
        return ""


@tool
def check_inventory_tool(item_name: str, as_of_date: str) -> int:
    """
    Returns the current stock level for a given item as of a specific date.
    Args:
        item_name (str): The exact name of the inventory item.
        as_of_date (str): The cutoff date in YYYY-MM-DD format.
    """
    stock_df = get_stock_level(db_engine, item_name, as_of_date)
    return int(stock_df.iloc[0]["current_stock"]) if not stock_df.empty else 0
