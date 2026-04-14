from smolagents import ToolCallingAgent
from src.tools.inventory_tools import check_inventory_tool, find_similar_inventory_item_tool
from src.tools.fulfillment_tools import fulfill_order_tool, get_delivery_timeline_tool
from src.tools.pricing_tools import get_item_unit_price
from src.tools.history_tools import get_customer_history_tool


class CustomerRelationshipAgent(ToolCallingAgent):
    """Specializes in retrieving customer history and context."""

    def __init__(self, model):
        super().__init__(
            name="customer_relationship_agent",
            description="You are a customer relationship specialist. Find past history related to a customer's inquiry.",
            tools=[get_customer_history_tool],
            model=model,
        )


class InventoryAgent(ToolCallingAgent):
    """Specializes in checking warehouse stock and delivery timelines."""

    def __init__(self, model):
        super().__init__(
            name="inventory_agent",
            description=(
                "You are an inventory management specialist. Answer questions about product stock levels and delivery timelines. "
                "You can also find similar items in inventory if the requested one is out of stock. "
                "Extract ONLY the simple item name before calling tools."
            ),
            tools=[check_inventory_tool, get_delivery_timeline_tool, find_similar_inventory_item_tool],
            model=model,
        )


class QuotationAgent(ToolCallingAgent):
    """Specializes in generating price quotes for customers."""

    def __init__(self, model):
        super().__init__(
            name="quotation_agent",
            description=(
                "You are a pricing specialist. Generate a quote for a customer. "
                "State if you are applying any discounts. Use get_item_unit_price tool to get the base prices. "
                "If an item is not directly found, you can try to find a similar one."
            ),
            tools=[get_item_unit_price, find_similar_inventory_item_tool],
            model=model,
        )


class SalesAgent(ToolCallingAgent):
    """Specializes in finalizing confirmed customer sales."""

    def __init__(self, model):
        super().__init__(
            name="sales_agent",
            description="You are a sales finalization specialist. Process confirmed sales by creating transaction records.",
            tools=[fulfill_order_tool],
            model=model,
        )


def create_specialized_agents(model) -> dict:
    """Instantiates all specialized sub-agents and returns them keyed by role."""
    return {
        "customer_relationship": CustomerRelationshipAgent(model),
        "inventory": InventoryAgent(model),
        "quotation": QuotationAgent(model),
        "sales": SalesAgent(model),
    }
