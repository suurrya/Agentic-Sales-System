import pandas as pd
from typing import List, Tuple
from smolagents import ToolCallingAgent, tool
from tools import (
    get_customer_history_tool, check_inventory_tool, get_delivery_timeline_tool,
    get_item_unit_price, fulfill_order_tool, parse_customer_request,
    find_similar_inventory_item_tool
)

class CustomerRelationshipAgent(ToolCallingAgent):
    """An agent specializing in customer history."""
    def __init__(self, model):
        super().__init__(
            name="customer_relationship_agent",
            description="You are a customer relationship specialist. Find past history related to a customer's inquiry.",
            tools=[get_customer_history_tool],
            model=model
        )

class InventoryAgent(ToolCallingAgent):
    """An agent specializing in warehouse stock."""
    def __init__(self, model):
        super().__init__(
            name="inventory_agent",
            description=(
                "You are an inventory management specialist. Answer questions about product stock levels and delivery timelines. "
                "You can also find similar items in inventory if the requested one is out of stock. "
                "Extract ONLY the simple item name before calling tools."
            ),
            tools=[check_inventory_tool, get_delivery_timeline_tool, find_similar_inventory_item_tool],
            model=model
        )

class QuotationAgent(ToolCallingAgent):
    """An agent specializing in generating price quotes."""
    def __init__(self, model):
        super().__init__(
            name="quotation_agent",
            description=(
                "You are a pricing specialist. Generate a quote for a customer. "
                "State if you are applying any discounts. Use get_item_unit_price tool to get the base prices. "
                "If an item is not directly found, you can try to find a similar one."
            ),
            tools=[get_item_unit_price, find_similar_inventory_item_tool],
            model=model
        )

class SalesAgent(ToolCallingAgent):
    """An agent specializing in finalizing customer sales."""
    def __init__(self, model):
        super().__init__(
            name="sales_agent",
            description="You are a sales finalization specialist. Process confirmed sales by creating transaction records.",
            tools=[fulfill_order_tool],
            model=model
        )

class CustomerAgent:
    """An agent that simulates a customer."""
    def __init__(self, request_data: pd.Series):
        self.request_text = request_data['request']
        self.is_non_profit = 'non-profit' in request_data['job'].lower()
        self.budget = 300 if self.is_non_profit else 150 
        self.negotiation_strategy = "flexible_timeline" if self.is_non_profit else "strict_budget"

    def get_initial_request(self, date: str) -> str:
        return f"{self.request_text} (Date of request: {date})"

    def evaluate_response(self, true_total_price: float) -> str:
        if 0 < true_total_price <= self.budget:
            return "yes"
        return "no, that is too expensive"

def create_specialized_agents(model):
    return {
        "customer_relationship": CustomerRelationshipAgent(model),
        "inventory": InventoryAgent(model),
        "quotation": QuotationAgent(model),
        "sales": SalesAgent(model)
    }

def create_orchestrator_tools(agents):
    @tool
    def customer_relationship_tool(request: str) -> str:
        """Essential historical context."""
        return agents["customer_relationship"](request)

    @tool
    def inventory_tool(request: str) -> str:
        """Check stock and delivery timelines."""
        return agents["inventory"](request)

    @tool
    def quotation_tool(request: str) -> str:
        """Generate a price quote."""
        return agents["quotation"](request)

    @tool
    def sales_tool(request: str) -> str:
        """Finalize the sale."""
        return agents["sales"](request)

    @tool
    def parse_customer_request_tool(request: str) -> List[Tuple[str, int]]:
        """Parse raw request into items and quantities."""
        return parse_customer_request(request)
    
    return [
        customer_relationship_tool,
        inventory_tool,
        quotation_tool,
        sales_tool,
        parse_customer_request_tool,
        get_item_unit_price,
        get_delivery_timeline_tool,
        find_similar_inventory_item_tool
    ]

class BestOrchestrator(ToolCallingAgent):
    """The master orchestrator agent."""
    def __init__(self, model, tools):
        super().__init__(
            name="orchestrator_agent",
            description=(
                "You are the master orchestrator of a sales team. Process customer requests and provide final outcomes. "
                "Determine if an order can be fulfilled, report stock/timelines, generate quotes, and finalize sales."
            ),
            tools=tools,
            model=model
        )
