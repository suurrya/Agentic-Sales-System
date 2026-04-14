from typing import List, Tuple
from smolagents import ToolCallingAgent, tool
from src.tools.inventory_tools import find_similar_inventory_item_tool
from src.tools.fulfillment_tools import get_delivery_timeline_tool
from src.tools.pricing_tools import get_item_unit_price
from src.utils.parsers import parse_customer_request


def create_orchestrator_tools(agents: dict) -> list:
    """
    Wraps each specialized agent as a @tool so the orchestrator can call them
    alongside direct utility tools.
    """

    @tool
    def customer_relationship_tool(request: str) -> str:
        """
        Retrieves essential historical context for a customer request.
        Args:
            request (str): The customer's request text.
        """
        return agents["customer_relationship"](request)

    @tool
    def inventory_tool(request: str) -> str:
        """
        Checks stock levels and delivery timelines for requested items.
        Args:
            request (str): A description of the item and date to check.
        """
        return agents["inventory"](request)

    @tool
    def quotation_tool(request: str) -> str:
        """
        Generates a price quote for one or more items.
        Args:
            request (str): A description of the items and quantities to quote.
        """
        return agents["quotation"](request)

    @tool
    def sales_tool(request: str) -> str:
        """
        Finalizes a confirmed sale and records the transaction.
        Args:
            request (str): A description of the order to fulfill including price.
        """
        return agents["sales"](request)

    @tool
    def parse_customer_request_tool(request: str) -> List[Tuple[str, int]]:
        """
        Parses a raw customer request string into a list of (item_name, quantity) tuples.
        Args:
            request (str): The raw customer request text.
        """
        return parse_customer_request(request)

    return [
        customer_relationship_tool,
        inventory_tool,
        quotation_tool,
        sales_tool,
        parse_customer_request_tool,
        get_item_unit_price,
        get_delivery_timeline_tool,
        find_similar_inventory_item_tool,
    ]


class BestOrchestrator(ToolCallingAgent):
    """Master orchestrator that coordinates all specialized agents to handle customer requests end-to-end."""

    def __init__(self, model, tools: list):
        super().__init__(
            name="orchestrator_agent",
            description=(
                "You are the master orchestrator of a sales team. Process customer requests and provide final outcomes. "
                "Determine if an order can be fulfilled, report stock/timelines, generate quotes, and finalize sales."
            ),
            tools=tools,
            model=model,
        )
