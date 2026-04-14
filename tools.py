import re
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union
from smolagents import tool
from database import (
    db_engine, get_stock_level, search_quote_history, create_transaction,
    get_all_inventory, get_cash_balance
)

def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """
    Estimates delivery date.
    """
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity}")
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        input_date_dt = datetime.now()

    if quantity <= 10: days = 0
    elif quantity <= 100: days = 1
    elif quantity <= 1000: days = 4
    else: days = 7
    return (input_date_dt + timedelta(days=days)).strftime("%Y-%m-%d")

def parse_price_from_quote(quote_response: str) -> float:
    """
    Extracts price from quote.
    """
    total_match = re.search(r'Total:\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', quote_response, re.IGNORECASE)
    if total_match:
        try:
            return float(total_match.group(1).replace(',', ''))
        except (ValueError, IndexError):
            return 0.0
    return 0.0

def parse_customer_request(request: str) -> List[Tuple[str, int]]:
    """
    Parses customer request for items and quantities.
    """
    items_found = []
    pattern = re.compile(
        r"([\d,]+)\s+(sheets?|reams?|packets?|rolls?|flyers?|posters?|tickets?|napkins?|plates?|cups?|cards?|envelopes?|tags?|folders?|bags?|streamers?)\s*(?:of\s*)?(.+?)(?=\s*,|\s+and|\s+along with|\.|$|\n)",
        re.IGNORECASE
    )
    for line in request.split('\n'):
        line = line.strip().lstrip('- ').strip()
        if not line: continue
        matches = pattern.findall(line)
        for match in matches:
            try:
                quantity_str, unit, item_name_raw = match
                quantity = int(quantity_str.replace(',', ''))
                if unit.lower().rstrip('s') in ['flyer', 'poster', 'ticket', 'napkin', 'plate', 'cup', 'card', 'envelope', 'tag', 'folder', 'bag', 'streamer']:
                     item_name = f"{item_name_raw.strip()} {unit.strip()}"
                else: item_name = item_name_raw.strip()
                item_name = re.sub(r'\s*\([^)]*\)', '', item_name).strip()
                item_name = " ".join(item_name.split())
                if item_name and len(item_name) > 1:
                    items_found.append((item_name, quantity))
            except (ValueError, IndexError): continue
    return items_found

def parse_date_from_timeline_response(response: str) -> str:
    """
    Parses date from timeline response.
    """
    months = "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    pattern = rf"{months}\s+\d{{1,2}},\s+\d{{4}}"
    match = re.search(pattern, response)
    if match: return match.group(0)
    match = re.search(r'\d{4}-\d{2}-\d{2}', response)
    if match: return match.group(0)
    return "Not Available"

def parse_transaction_id(sales_agent_response: str) -> str:
    """
    Parses transaction ID.
    """
    match = re.search(r'transaction ID(?: of|:) (\d+)', sales_agent_response)
    return match.group(1) if match else "N/A"

def parse_stock_level_from_response(response: str) -> int:
    """
    Parses stock level.
    """
    match = re.search(r'(?:is|have|stock:|quantity)\s*([\d,]+)', response, re.IGNORECASE)
    if not match: match = re.search(r'(\d[\d,]*)', response)
    if match:
        try: return int(match.group(1).replace(',', ''))
        except (ValueError, IndexError): pass
    return 0

@tool
def find_similar_inventory_item_tool(search_term: str) -> str:
    """
    Finds best matching item in inventory.
    Args:
        search_term (str): The search term.
    """
    keywords = set(re.findall(r'\w+', search_term.lower()))
    if not keywords: return ""
    try:
        all_items = pd.read_sql("SELECT item_name FROM inventory", db_engine)
        if all_items.empty: return ""
        best_match, highest_score = None, 0
        for item_name in all_items["item_name"]:
            item_words = set(re.findall(r'\w+', item_name.lower()))
            score = len(keywords.intersection(item_words))
            if score > highest_score: highest_score, best_match = score, item_name
            elif score == highest_score and best_match and len(item_name) < len(best_match): best_match = item_name
        return best_match if highest_score > 0 else ""
    except: return ""

@tool
def check_inventory_tool(item_name: str, as_of_date: str) -> int:
    """
    Checks stock.
    Args:
        item_name (str): The item name.
        as_of_date (str): Cutoff date.
    """
    stock_df = get_stock_level(db_engine, item_name, as_of_date)
    return int(stock_df.iloc[0]["current_stock"]) if not stock_df.empty else 0

@tool
def get_delivery_timeline_tool(quantity: int) -> str:
    """
    Estimates delivery.
    Args:
        quantity (int): Number of units.
    """
    return get_supplier_delivery_date(datetime.now().isoformat(), quantity)

@tool
def get_customer_history_tool(search_terms: List[str]) -> List[Dict]:
    """
    Searches history.
    Args:
        search_terms (List[str]): Keywords.
    """
    return search_quote_history(db_engine, search_terms, limit=3)

@tool
def fulfill_order_tool(item_name: str, quantity: int, price: float, date: str) -> int:
    """
    Fulfills order.
    Args:
        item_name (str): Item name.
        quantity (int): Quantity.
        price (float): Total price.
        date (str): Date.
    """
    return create_transaction(db_engine, item_name, "sales", quantity, price, date)

@tool
def get_full_inventory_report_tool() -> Dict[str, int]:
    """
    Full inventory report.
    """
    return get_all_inventory(db_engine, datetime.now().isoformat())

@tool
def get_current_cash_balance_tool() -> float:
    """
    Current cash balance.
    """
    return get_cash_balance(db_engine, datetime.now().isoformat())

@tool
def get_item_unit_price(item_name: str) -> float:
    """
    Retrieves item unit price.
    Args:
        item_name (str): Item name.
    """
    try:
        price_df = pd.read_sql("SELECT unit_price FROM inventory WHERE item_name = :item", db_engine, params={"item": item_name})
        return float(price_df.iloc[0]["unit_price"]) if not price_df.empty else 0.0
    except: return 0.0
