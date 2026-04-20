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

from json_repair import repair_json
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


# ── JSON extraction helpers ───────────────────────────────────────────────────

def _extract_nested_json(text: str) -> Optional[dict]:
    """Like _extract_json but handles nested structures (lists inside objects).

    Walks the string to find balanced braces rather than using a regex that
    forbids inner braces.  Used by llm_parse_request where the agent returns
    {"items": [{"item_name": ..., "quantity": N}, ...]}.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    try:
                        repaired = repair_json(blob, ensure_ascii=False, return_objects=False)
                        return json.loads(repaired)
                    except Exception:
                        return None
    return None


def _extract_json(text: str) -> Optional[dict]:
    """Searches text for the first JSON object and parses it.

    Three-layer approach:
    1. json.loads on the raw extracted blob (zero overhead for valid JSON).
    2. json-repair on the blob (fixes single quotes, trailing commas, etc.).
    3. Returns None if both layers fail, letting the regex fallback take over.

    Args:
        text: Any string, typically an LLM agent response.

    Returns:
        Parsed dict if a valid JSON object was found, otherwise None.
    """
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    blob = match.group()

    # Layer 1: standard parse (fastest path)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        pass

    # Layer 2: repair then parse
    try:
        repaired = repair_json(blob, ensure_ascii=False, return_objects=False)
        return json.loads(repaired)
    except (json.JSONDecodeError, Exception):
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

    # Regex fallback — two patterns handle the two natural-language styles:
    #
    # Style A: "500 sheets of A4 paper"  (quantity + unit-word + item name)
    #   The unit-word list identifies the boundary; item name follows.
    #   When no item name follows the unit word (e.g. "300 envelopes"),
    #   the unit word itself becomes the item name.
    #
    # Style B: "1000 flyers" / "2000 disposable cups" / "50 table covers"
    #   (quantity + descriptive prefix? + known product-ending keyword)
    #   The prefix is fully optional so single-word products like "napkins"
    #   or "envelopes" are captured correctly.
    #
    # Shared terminator lookahead stops at: comma, "and", "for", "along with",
    # sentence-ending punctuation, opening parenthesis, or end-of-string.
    _STOP = r"(?=\s*,|\s+and\b|\s+for\b|\s+along with\b|\.|[?!]|$|\n|\s*\()"

    items_found = []

    # ── Style A ──────────────────────────────────────────────────────────────
    _UNIT_WORDS = (
        r"sheets?|reams?|packets?|rolls?|cards?|envelopes?|folders?"
        r"|bags?|streamers?|covers?|notepads?|tags?"
    )
    pattern_a = re.compile(
        r"(\d[\d,]*)\s+"
        rf"({_UNIT_WORDS})\s*"
        r"(?:of\s+)?(.*?)" + _STOP,
        re.IGNORECASE,
    )

    # ── Style B ──────────────────────────────────────────────────────────────
    # Known product-ending keywords.  The optional prefix `(?:...\s+)?` allows
    # both "napkins" (no prefix) and "paper napkins" / "disposable cups" (with
    # prefix) to be captured by the same rule.
    _PRODUCT_ENDINGS = (
        r"flyers?|posters?|tickets?|napkins?|plates?|cups?|folders?"
        r"|notes?|bags?|covers?|cards?|envelopes?|papers?\b[^,]*?"
    )
    pattern_b = re.compile(
        r"(\d[\d,]*)\s+"
        r"(?:of\s+)?"
        r"((?:disposable\s+)?(?:large\s+|small\s+|sticky\s+)?"
        rf"(?:[a-zA-Z][a-zA-Z0-9 \-]*?\s+)?(?:{_PRODUCT_ENDINGS}))"
        + _STOP,
        re.IGNORECASE,
    )

    full_text = " ".join(request.split("\n"))  # flatten to single line

    # Unit-word stripper: removes leading "sheets of" / "rolls of" etc. from
    # Pattern B results so they don't duplicate Style A captures.
    _leading_unit = re.compile(
        rf"^(?:{_UNIT_WORDS})\s+(?:of\s+)?", re.IGNORECASE
    )

    seen: set = set()

    # ── Run Style A first ─────────────────────────────────────────────────────
    for match in pattern_a.finditer(full_text):
        try:
            quantity_str, unit_word, item_name_raw = match.groups()
            quantity = int(quantity_str.replace(",", ""))
            item_name = item_name_raw.strip()
            item_name = re.sub(r"\s*\([^)]*\)", "", item_name).strip()  # strip parentheticals
            item_name = " ".join(item_name.split())
            # "300 envelopes" → unit="envelopes", item="" → use unit word as name
            if not item_name:
                item_name = unit_word.strip()
            if len(item_name) > 1 and (item_name, quantity) not in seen:
                items_found.append((item_name, quantity))
                seen.add((item_name, quantity))
        except (ValueError, IndexError):
            continue

    # ── Run Style B, deduplicating against Style A ───────────────────────────
    for match in pattern_b.finditer(full_text):
        try:
            quantity_str, item_name_raw = match.groups()
            quantity = int(quantity_str.replace(",", ""))
            item_name = item_name_raw.strip()
            item_name = re.sub(r"\s*\([^)]*\)", "", item_name).strip()
            item_name = " ".join(item_name.split())
            # Strip leading unit words so "sheets of A4 paper" normalises to
            # "A4 paper" and is recognised as already captured by Style A.
            normalised = _leading_unit.sub("", item_name).strip()
            if len(item_name) > 1 and (normalised, quantity) not in seen and (item_name, quantity) not in seen:
                items_found.append((item_name, quantity))
                seen.add((item_name, quantity))
                seen.add((normalised, quantity))
        except (ValueError, IndexError):
            continue

    return items_found


def parse_price_from_quote(quote_response) -> float:
    """Extracts the total price from a QuotationAgent response.

    Tries JSON QuoteResult first; falls back to a regex matching
    "Total: $X,XXX.XX" patterns.

    Args:
        quote_response: Raw response from the quotation agent — may be a str,
                        int, or float when the LLM returns a bare number as
                        its final_answer (e.g. {'answer': 20}).

    Returns:
        Float total price in USD, or 0.0 if no price could be extracted.
    """
    # Agent returned a bare numeric answer (int or float) — use it directly.
    if isinstance(quote_response, (int, float)):
        return float(quote_response)

    # Coerce anything else (None, list, …) to a safe empty string.
    if not isinstance(quote_response, str):
        quote_response = ""

    data = _extract_json(quote_response)
    if data:
        try:
            return QuoteResult(**data).total_amount
        except Exception:
            pass

    _PRICE_RE = r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"

    # Pattern 1: "Total: $1,234.56" (structured agent output)
    total_match = re.search(r"Total:\s*" + _PRICE_RE, quote_response, re.IGNORECASE)
    if total_match:
        try:
            return float(total_match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            pass

    # Pattern 2: "= $21.50" — collect all occurrences and take the last one,
    # which is the cumulative total in LLM-style "X + Y = Z" breakdowns.
    eq_amounts = re.findall(r"=\s*" + _PRICE_RE, quote_response, re.IGNORECASE)
    if eq_amounts:
        try:
            return float(eq_amounts[-1].replace(",", ""))
        except (ValueError, IndexError):
            pass

    # Pattern 3: bare "total (cost|price) … $X.XX" as a last resort
    loose_match = re.search(
        r"total(?:\s+\w+){0,4}\s+" + _PRICE_RE, quote_response, re.IGNORECASE
    )
    if loose_match:
        try:
            return float(loose_match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            pass

    _BARE_NUM = r"([\d,]+(?:\.\d+)?)"

    # Pattern 4: last bare "= NUMBER" — catches LLM math breakdowns like
    # "48 + 1050 + 70 + 60 = 1228" where the final = is the running total.
    eq_bare = re.findall(r"=\s*" + _BARE_NUM, quote_response)
    if eq_bare:
        try:
            return float(eq_bare[-1].replace(",", ""))
        except (ValueError, IndexError):
            pass

    # Pattern 5: "total price is: NUMBER" — handles optional colon/punctuation
    # after "is" so "price is: 1228" and "price is 1228" both match.
    bare_matches = re.findall(
        r"(?:total|price|cost|amount)\b[^$\n]*?\bis[\s:]+\s*" + _BARE_NUM,
        quote_response, re.IGNORECASE,
    )
    if bare_matches:
        try:
            return float(bare_matches[-1].replace(",", ""))
        except (ValueError, IndexError):
            pass

    # Pattern 6: "Price: 50.00" — label immediately followed by a bare number (no open paren)
    label_match = re.search(
        r"(?:price|cost|total|amount)\s*:\s*(?!\()" + _BARE_NUM,
        quote_response, re.IGNORECASE,
    )
    if label_match:
        try:
            return float(label_match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            pass

    # Pattern 6: "50 dollars" / "50.00 dollars"
    dollars_match = re.search(
        r"\b" + _BARE_NUM + r"\s+dollars\b",
        quote_response, re.IGNORECASE,
    )
    if dollars_match:
        try:
            return float(dollars_match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            pass

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

    # Regex fallback — several patterns the sales agent commonly produces:
    # Pattern 1: "transaction ID of X" / "transaction ID: X" / "Transaction IDs: X, Y"
    match = re.search(r"[Tt]ransaction\s+IDs?[:\s]+(\d+)", sales_agent_response)
    if match:
        return match.group(1)

    # Pattern 2: "ID 42" / "ID: 42" — bare ID reference
    match = re.search(r"\bID[:\s]+(\d+)", sales_agent_response)
    if match:
        return match.group(1)

    # Pattern 3: the tool returns a raw integer; agent may echo it as "returns 42" or just "42."
    match = re.search(r"\breturns?\s+(\d+)", sales_agent_response, re.IGNORECASE)
    if match:
        return match.group(1)

    return "N/A"


def llm_parse_request(request_text: str, parser_agent) -> List[Tuple[str, int]]:
    """Fallback parser that uses an LLM agent when the regex parser returns nothing.

    Only called when parse_customer_request() returns [].  The agent receives the
    raw request, normalises spelling/descriptions, and returns a JSON string:
        {"items": [{"item_name": "Colored paper", "quantity": 200}, ...]}

    Uses _extract_nested_json (not _extract_json) because the items list creates
    nested braces that the flat-object regex cannot match.

    Args:
        request_text: Raw customer request string.
        parser_agent: An instantiated RequestParserAgent (or any agent whose
                      .run() returns a string containing the items JSON).

    Returns:
        List of (item_name, quantity) tuples, or [] if the LLM also fails.
    """
    try:
        response = parser_agent.run(
            f"Extract all products and quantities from this customer request: {request_text}"
        )
        data = _extract_nested_json(str(response))
        if not data:
            return []
        items = data.get("items", [])
        if not isinstance(items, list):
            return []
        result = []
        for item in items:
            try:
                name = str(item["item_name"]).strip()
                qty = int(item["quantity"])
                if name and qty > 0:
                    result.append((name, qty))
            except (KeyError, ValueError, TypeError):
                continue
        return result
    except Exception as exc:
        print(f"[LLM PARSER] Failed: {exc}")
        return []
