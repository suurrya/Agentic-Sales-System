"""
specialized.py
==============
Defines all four specialised sub-agents used in the Munder Difflin pipeline.

Each agent is a smolagents ToolCallingAgent configured with a focused system prompt
and a minimal tool set that matches its single responsibility:

    CustomerRelationshipAgent — retrieves past quote history for context
    InventoryAgent            — checks live stock levels and delivery timelines
    QuotationAgent            — builds itemised price quotes with optional discounts
    SalesAgent                — commits confirmed orders as database transactions

All four agents are instantiated together by create_specialized_agents() and returned
as a dict keyed by role name, which is then passed to create_orchestrator_tools().
"""

from smolagents import ToolCallingAgent

from src.agents.prompts import CUSTOMER_RELATIONSHIP_PROMPT, INVENTORY_PROMPT, QUOTATION_PROMPT, SALES_PROMPT, REQUEST_PARSER_PROMPT
from src.tools.fulfillment_tools import fulfill_order_tool, get_delivery_timeline_tool
from src.tools.history_tools import get_customer_history_tool
from src.tools.inventory_tools import check_inventory_tool, find_similar_inventory_item_tool
from src.tools.pricing_tools import get_item_unit_price


class RequestParserAgent(ToolCallingAgent):
    """LLM fallback parser — only invoked when the regex parser returns nothing.

    Has no tools beyond final_answer. Given a free-form customer request it
    normalises spelling (coloured → colored), resolves informal descriptions,
    and returns a JSON string: {"items": [{"item_name": "...", "quantity": N}]}.

    Keeping it as a ToolCallingAgent (rather than a direct model call) means it
    reuses ResilientOpenAIModel's retry logic and the existing json-repair patches.
    """

    def __init__(self, model):
        super().__init__(
            name="request_parser_agent",
            tools=[],
            model=model,
            max_steps=2,
            instructions=REQUEST_PARSER_PROMPT,
        )


class CustomerRelationshipAgent(ToolCallingAgent):
    """Retrieves historical quote data relevant to the current customer request.

    Uses get_customer_history_tool to search the quotes and quote_requests tables
    for past orders matching keywords from the incoming request. The results are
    passed back to the orchestrator as context before pricing begins.

    Tools available: get_customer_history_tool
    """

    def __init__(self, model):
        """Args:
            model: A smolagents-compatible LLM model instance.
        """
        super().__init__(
            name="customer_relationship_agent",
            description=CUSTOMER_RELATIONSHIP_PROMPT,
            tools=[get_customer_history_tool],
            model=model,
            max_steps=4,
        )


class InventoryAgent(ToolCallingAgent):
    """Checks warehouse stock levels and estimates delivery timelines.

    Given an item name (or description), this agent verifies whether sufficient
    stock exists as of the requested date. If the exact item is not found, it uses
    find_similar_inventory_item_tool to suggest the closest catalogue match.

    Tools available: check_inventory_tool, get_delivery_timeline_tool,
                     find_similar_inventory_item_tool
    """

    def __init__(self, model):
        """Args:
            model: A smolagents-compatible LLM model instance.
        """
        super().__init__(
            name="inventory_agent",
            description=INVENTORY_PROMPT,
            tools=[check_inventory_tool, get_delivery_timeline_tool, find_similar_inventory_item_tool],
            model=model,
            max_steps=6,
        )


class QuotationAgent(ToolCallingAgent):
    """Generates itemised price quotes, with optional discounts applied.

    Uses get_item_unit_price to look up base prices per item. If an exact item name
    is not found, it can fall back to find_similar_inventory_item_tool to match
    the closest catalogue entry before pricing.

    Tools available: get_item_unit_price, find_similar_inventory_item_tool
    """

    def __init__(self, model):
        """Args:
            model: A smolagents-compatible LLM model instance.
        """
        super().__init__(
            name="quotation_agent",
            tools=[get_item_unit_price, find_similar_inventory_item_tool],
            model=model,
            max_steps=8,
            instructions=QUOTATION_PROMPT,
        )


class SalesAgent(ToolCallingAgent):
    """Finalises confirmed customer sales by writing transaction records to the database.

    Called only after the customer has accepted a quote. Uses fulfill_order_tool to
    insert a "sales" transaction row via create_transaction(), which returns the
    auto-assigned transaction ID logged in the OLTP output.

    Tools available: fulfill_order_tool
    """

    def __init__(self, model):
        """Args:
            model: A smolagents-compatible LLM model instance.
        """
        super().__init__(
            name="sales_agent",
            tools=[fulfill_order_tool],
            model=model,
            max_steps=6,
            instructions=SALES_PROMPT,
        )


def create_specialized_agents(model) -> dict:
    """Instantiates all four specialised sub-agents and returns them keyed by role.

    Args:
        model: A smolagents-compatible LLM model instance shared across all agents.

    Returns:
        Dict with keys: "customer_relationship", "inventory", "quotation", "sales".
        Each value is the corresponding instantiated agent.
    """
    return {
        "parser": RequestParserAgent(model),
        "customer_relationship": CustomerRelationshipAgent(model),
        "inventory": InventoryAgent(model),
        "quotation": QuotationAgent(model),
        "sales": SalesAgent(model),
    }
