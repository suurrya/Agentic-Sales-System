import re
from datetime import datetime, timedelta
from typing import List, Tuple


def parse_customer_request(request: str) -> List[Tuple[str, int]]:
    """Parses a free-text customer request into a list of (item_name, quantity) tuples."""
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
                if unit.lower().rstrip("s") in [
                    "flyer", "poster", "ticket", "napkin", "plate", "cup",
                    "card", "envelope", "tag", "folder", "bag", "streamer",
                ]:
                    item_name = f"{item_name_raw.strip()} {unit.strip()}"
                else:
                    item_name = item_name_raw.strip()
                item_name = re.sub(r"\s*\([^)]*\)", "", item_name).strip()
                item_name = " ".join(item_name.split())
                if item_name and len(item_name) > 1:
                    items_found.append((item_name, quantity))
            except (ValueError, IndexError):
                continue
    return items_found


def parse_price_from_quote(quote_response: str) -> float:
    """Extracts the total price from a quote string using regex."""
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
    """Extracts a stock quantity from a natural-language agent response."""
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
    """Extracts a delivery date from a timeline agent response."""
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
    """Extracts a transaction ID from a sales agent response."""
    match = re.search(r"transaction ID(?: of|:) (\d+)", sales_agent_response)
    return match.group(1) if match else "N/A"
