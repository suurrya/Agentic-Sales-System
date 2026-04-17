"""
inventory_tools.py
==================
smolagents tools for querying warehouse stock levels and finding catalogue matches.

Exposed tools:
    find_similar_inventory_item_tool — fuzzy keyword-overlap item name matching
    check_inventory_tool             — exact stock level lookup for a date
"""

import re
from difflib import SequenceMatcher

import pandas as pd
from smolagents import tool

from src.database.database import db_engine, get_stock_level


def _item_score(search_words: list[str], item_name: str) -> float:
    """Score a catalogue item name against a list of search words.

    For each search word we find the best character-level similarity to any
    word in the item name (via SequenceMatcher).  Exact matches contribute 2.0;
    near-matches (e.g. "coloured" vs "colored") contribute their similarity
    ratio (~0.93).  The total is divided by the number of search words so
    scores are comparable across items regardless of length.

    This handles:
    - Spelling variants:  "coloured" → "colored",  "grey" → "gray"
    - Plurals / suffixes: "papers" → "paper",  "envelop" → "envelope"
    - Partial matches:    "folder" → "presentation folders"
    """
    item_words = re.findall(r"\w+", item_name.lower())
    if not item_words:
        return 0.0
    total = 0.0
    for sw in search_words:
        if sw in item_words:
            total += 2.0  # exact word match — counts double
        else:
            best = max(
                SequenceMatcher(None, sw, iw).ratio() for iw in item_words
            )
            total += best
    return total / len(search_words)


@tool
def find_similar_inventory_item_tool(search_term: str) -> str:
    """
    Finds the best matching item name in the inventory catalogue.
    Uses character-level similarity (difflib SequenceMatcher) so spelling
    variants like "coloured/colored", "grey/gray", and minor typos are handled
    correctly. Exact word matches are weighted double over partial matches.
    Returns an empty string if no reasonable match is found.
    Args:
        search_term (str): A description or partial name of the item to search for.
    """
    search_words = re.findall(r"\w+", search_term.lower())
    if not search_words:
        return ""
    try:
        all_items = pd.read_sql("SELECT item_name FROM inventory", db_engine)
        if all_items.empty:
            return ""
        best_match, best_score = None, 0.0
        for item_name in all_items["item_name"]:
            score = _item_score(search_words, item_name)
            if score > best_score:
                best_score, best_match = score, item_name
        # Require at least one meaningful match (threshold: 0.5 per search word)
        return best_match if best_score >= 0.5 else ""
    except Exception as e:
        print(f"Error searching inventory: {e}")
        return ""


@tool
def check_inventory_tool(item_name: str, as_of_date: str) -> int:
    """
    Returns the current stock level for a given item as of a specific date.
    Stock is computed from transactions up to and including as_of_date,
    so historical snapshots can be queried by passing any past date.
    Args:
        item_name (str): The exact name of the inventory item.
        as_of_date (str): The cutoff date in YYYY-MM-DD format.
    """
    stock_df = get_stock_level(db_engine, item_name, as_of_date)
    return int(stock_df.iloc[0]["current_stock"]) if not stock_df.empty else 0
