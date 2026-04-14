from typing import Dict, List
from smolagents import tool
from src.database.database import db_engine, search_quote_history


@tool
def get_customer_history_tool(search_terms: List[str]) -> List[Dict]:
    """
    Searches the quote history database for records matching the given keywords.
    Args:
        search_terms (List[str]): A list of keywords to search for in past quotes and requests.
    """
    return search_quote_history(db_engine, search_terms, limit=3)
