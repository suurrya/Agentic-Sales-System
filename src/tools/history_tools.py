"""
history_tools.py
================
smolagents tool for searching past quote history.

Exposed tool:
    get_customer_history_tool — keyword search over the quotes + quote_requests tables
"""

from typing import Dict, List

from smolagents import tool

from src.database.database import db_engine, search_quote_history


@tool
def get_customer_history_tool(search_terms: List[str]) -> List[Dict]:
    """
    Searches the quote history database for records matching the given keywords.
    Returns an empty list immediately if no search terms are provided,
    preventing an unfiltered full-table scan.
    Args:
        search_terms (List[str]): A list of keywords to search for in past quotes and requests.
    """
    if not search_terms:
        return []
    return search_quote_history(db_engine, search_terms, limit=3)
