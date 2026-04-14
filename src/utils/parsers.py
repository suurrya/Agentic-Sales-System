"""
parsers.py
==========
Structured output parsing for all agent response boundaries.

Strategy: every parse function tries to extract a JSON object from the response text
first and validate it against a Pydantic schema. If that fails (malformed JSON,
missing required fields, validation error) the function falls back to a hand-rolled
regex that matches natural-language patterns produced by the LLM.

This two-layer approach means:
- Agents that return well-formed JSON get zero-cost, schema-validated parsing.
- Agents that return natural language still work without any changes.
- Adding strict JSON output prompts to agents in future is a drop-in improvement.

Pydantic schemas defined here:
    ParsedItem       — single (item_name, quantity) pair
    ParsedRequest    — list of ParsedItems for a full order
    QuoteResult      — total_amount + optional explanation
    StockResult      — item_name + current_stock
    DeliveryResult   — estimated_date string
    TransactionResult — transaction_id string
"""

import json
import re
from typing import List, Optional, Tuple

from pydantic import BaseModel, field_validator


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ParsedItem(BaseModel):
    """A single line item in a customer order: one product and its quantity.

    Attributes:
        item_name: Exact or approximate name of the inventory item.
        quantity: Number of units requested. Must be a positive integer.
    """

    item_name: str
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        """Rejects zero or negative quantities at parse time."""
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class ParsedRequest(BaseModel):
    """A complete parsed customer order containing one or more line items.

    Attributes:
        items: List of ParsedItem objects extracted from the request text.
    """

    items: List[ParsedItem]


class QuoteResult(BaseModel):
    """Structured representation of a price quote returned by the QuotationAgent.

    Attributes:
        total_amount: Total quoted price in USD. Must be non-negative.
        explanation: Optional human-readable breakdown of the quote.
    """

    total_amount: float
    explanation: str = ""

    @field_validator("total_amount")
    @classmethod
    def amount_must_be_non_negative(cls, v: float) -> float:
        """Rejects negative prices at parse time."""
        if v < 0:
            raise ValueError("total_amount must be non-negative")
        return v


class StockResult(BaseModel):
    """Structured stock level response from the InventoryAgent.

    Attributes:
        item_name: Name of the inventory item queried.
        current_stock: Net units available as of the queried date.
    """

    item_name: str
    current_stock: int


class DeliveryResult(BaseModel):
    """Structured delivery timeline response from the InventoryAgent.

    Attributes:
        estimated_date: Estimated delivery date as a human-readable or ISO string.
    """

    estimated_date: str


class TransactionResult(BaseModel):
    """Structured sale confirmation response from the SalesAgent.

    Attributes:
        transaction_id: The database row ID of the committed transaction.
    """

    transaction_id: str


# ── JSON extraction helper ────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[dict]:
    """Searches text for the first JSON object and parses it.

    Uses a non-nested brace regex, so deeply nested JSON objects may not be
    captured correctly. Sufficient for the flat schemas used in this project.

    Args:
        text: Any string, typically an LLM agent response.

    Returns:
        Parsed dict if a valid JSON object was found, otherwise None.
    """
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ── Parse functions (JSON-first, regex fallback) ──────────────────────────────

def parse_customer_request(request: str) -> List[Tuple[str, int]]:
    """Converts a free-text customer request into a list of (item_name, quantity) tuples.

    Tries to extract a JSON object matching ParsedRequest first. Falls back to a
    regex that recognises quantity + unit + item patterns across multiple lines.

    Args:
        request: Raw customer request text, possibly multi-line.

    Returns:
        List of (item_name, quantity) tuples. Empty list if nothing was parsed.
    """
    # JSON path — agent may have returned structured output
    data = _extract_json(request)
    if data and "items" in data:
        try:
            parsed = ParsedRequest(**data)
            return [(item.item_name, item.quantity) for item in parsed.items]
        except Exception:
            pass

    # Regex fallback — matches "500 sheets of A4 paper" style patterns
    items_found = []
    pattern = re.compile(
        r"([\d,]+)\s+(sheets?|reams?|packets?|rolls?|flyers?|posters?|tickets?|napkins?|plates?|cups?|cards?|envelopes?|tags?|folders?|bags?|streamers?)\s*(?:of\s*)?(.+?)(?=\s*,|\s+and|\s+along with|\.|$|\n)",
        re.IGNORECASE,
    )
    for line in request.split("\n"):
        line = line.strip().lstrip("- ").strip()
        if not line:
            continue
        matches = pattern.findall(line)
        for match in matches:
            try:
                quantity_str, unit, item_name_raw = match
                quantity = int(quantity_str.replace(",", ""))
                # For discrete product units (flyers, plates, etc.) append the unit word
                if unit.lower().rstrip("s") in [
                    "flyer", "poster", "ticket", "napkin", "plate", "cup",
                    "card", "envelope", "tag", "folder", "bag", "streamer",
                ]:
                    item_name = f"{item_name_raw.strip()} {unit.strip()}"
                else:
                    item_name = item_name_raw.strip()
                # Strip parenthetical annotations and collapse whitespace
                item_name = re.sub(r"\s*\([^)]*\)", "", item_name).strip()
                item_name = " ".join(item_name.split())
                if item_name and len(item_name) > 1:
                    items_found.append((item_name, quantity))
            except (ValueError, IndexError):
                continue
    return items_found


def parse_price_from_quote(quote_response: str) -> float:
    """Extracts the total price from a QuotationAgent response.

    Tries JSON QuoteResult first; falls back to a regex matching
    "Total: $X,XXX.XX" patterns.

    Args:
        quote_response: Raw string response from the quotation agent.

    Returns:
        Float total price in USD, or 0.0 if no price could be extracted.
    """
    data = _extract_json(quote_response)
    if data:
        try:
            return QuoteResult(**data).total_amount
        except Exception:
            pass

    # Regex fallback — matches "Total: $1,234.56" style lines
    total_match = re.search(
        r"Total:\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", quote_response, re.IGNORECASE
    )
    if total_match:
        try:
            return float(total_match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            return 0.0
    return 0.0


def parse_stock_level_from_response(response: str) -> int:
    """Extracts a stock quantity from a natural-language InventoryAgent response.

    Tries JSON StockResult first; falls back to regex patterns that look for
    keywords like "stock:", "have", "is" followed by a number.

    Args:
        response: Raw string response from the inventory agent.

    Returns:
        Integer stock level, or 0 if nothing could be parsed.
    """
    data = _extract_json(response)
    if data:
        try:
            return StockResult(**data).current_stock
        except Exception:
            pass

    # Regex fallback — looks for contextual number patterns
    match = re.search(r"(?:is|have|stock:|quantity)\s*([\d,]+)", response, re.IGNORECASE)
    if not match:
        match = re.search(r"(\d[\d,]*)", response)
    if match:
        try:
            return int(match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            pass
    return 0


def parse_date_from_timeline_response(response: str) -> str:
    """Extracts a delivery date from a timeline agent response.

    Tries JSON DeliveryResult first; falls back to regex patterns that match
    "Month DD, YYYY" or ISO "YYYY-MM-DD" formats.

    Args:
        response: Raw string response from the fulfillment / inventory agent.

    Returns:
        Date string (human-readable or ISO), or "Not Available" if nothing found.
    """
    data = _extract_json(response)
    if data:
        try:
            return DeliveryResult(**data).estimated_date
        except Exception:
            pass

    # Regex fallback — tries long-form month first, then ISO
    months = "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    pattern = rf"{months}\s+\d{{1,2}},\s+\d{{4}}"
    match = re.search(pattern, response)
    if match:
        return match.group(0)
    match = re.search(r"\d{4}-\d{2}-\d{2}", response)
    if match:
        return match.group(0)
    return "Not Available"


def parse_transaction_id(sales_agent_response: str) -> str:
    """Extracts a transaction ID from a SalesAgent response.

    Tries JSON TransactionResult first; falls back to regex matching
    "transaction ID of X" or "transaction ID: X" patterns.

    Args:
        sales_agent_response: Raw string response from the sales agent.

    Returns:
        Transaction ID string, or "N/A" if nothing could be extracted.
    """
    data = _extract_json(sales_agent_response)
    if data:
        try:
            return TransactionResult(**data).transaction_id
        except Exception:
            pass

    # Regex fallback
    match = re.search(r"transaction ID(?: of|:) (\d+)", sales_agent_response)
    return match.group(1) if match else "N/A"
