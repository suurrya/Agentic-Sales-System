"""
orchestrator.py
===============
Master orchestrator agent and supporting infrastructure for the Munder Difflin
sales pipeline.

Key components:
- _with_retry     — exponential backoff wrapper for all agent tool calls
- _gather_context — async helper that fires history + inventory lookups in parallel
- create_orchestrator_tools — factory that wraps every sub-agent as a @tool
- BestOrchestrator — the top-level ToolCallingAgent that plans the full workflow
"""

import asyncio
import time
from typing import List, Tuple

from smolagents import ToolCallingAgent, tool

from src.tools.fulfillment_tools import get_delivery_timeline_tool
from src.tools.inventory_tools import find_similar_inventory_item_tool
from src.tools.pricing_tools import get_item_unit_price
from src.utils.logger import AgentFailureLogger
from src.utils.parsers import parse_customer_request

# Module-level failure logger shared by all retry wrappers
_failure_logger = AgentFailureLogger()


def _with_retry(fn, agent_name: str, request_id: int = 0, max_attempts: int = 3, base_delay: float = 1.0):
    """Wraps a callable with exponential backoff and structured failure logging.

    On each failed attempt the error is written to the JSONL failure log via
    AgentFailureLogger, then the wrapper sleeps for base_delay * 2^(attempt-1)
    seconds before retrying. After all attempts are exhausted a graceful fallback
    string is returned so the orchestrator pipeline can continue rather than crash.

    Args:
        fn: The callable to protect (typically an agent's __call__ method).
        agent_name: Human-readable name used in log messages and failure records.
        request_id: Current batch request ID, forwarded to the failure logger.
        max_attempts: Total number of attempts before giving up. Default 3.
        base_delay: Base sleep time in seconds; doubles each attempt. Default 1.0.

    Returns:
        A wrapped callable with the same signature as fn.
    """
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                _failure_logger.log(agent_name, request_id, attempt, e)
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    print(
                        f"[RETRY] {agent_name} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
        print(f"[FALLBACK] {agent_name} exhausted all {max_attempts} attempts.")
        return f"Agent '{agent_name}' unavailable after {max_attempts} attempts — {last_exc}"
    return wrapper


async def _gather_context(history_fn, inventory_fn, request: str) -> tuple:
    """Runs customer history lookup and inventory check concurrently in threads.

    Because both underlying agent calls are synchronous (blocking LLM requests),
    they are dispatched into the default ThreadPoolExecutor via run_in_executor so
    that asyncio.gather() can wait for both simultaneously rather than sequentially.

    Args:
        history_fn: Callable for the customer relationship agent (already retry-wrapped).
        inventory_fn: Callable for the inventory agent (already retry-wrapped).
        request: Raw customer request string passed to both agents.

    Returns:
        Tuple of (history_result, inventory_result) as strings.
    """
    loop = asyncio.get_running_loop()
    history, inventory = await asyncio.gather(
        loop.run_in_executor(None, history_fn, request),
        loop.run_in_executor(None, inventory_fn, request),
    )
    return history, inventory


def create_orchestrator_tools(agents: dict) -> list:
    """Wraps each specialised sub-agent as a smolagents @tool and returns the full
    tool list for the BestOrchestrator.

    The returned tools include:
        gather_context_tool        — parallel history + inventory (preferred)
        customer_relationship_tool — history only (fallback)
        inventory_tool             — inventory only (fallback)
        quotation_tool             — price quote generation
        sales_tool                 — transaction finalisation
        parse_customer_request_tool — free-text → [(item, qty)] parsing
        get_item_unit_price        — single-item price lookup
        get_delivery_timeline_tool — delivery date estimation
        find_similar_inventory_item_tool — fuzzy item name matching

    All agent-backed tools are wrapped with _with_retry for automatic recovery.

    Args:
        agents: Dict of instantiated sub-agents keyed by role name:
                "customer_relationship", "inventory", "quotation", "sales".

    Returns:
        List of smolagents tool objects ready to pass to BestOrchestrator.
    """

    @tool
    def gather_context_tool(request: str) -> str:
        """
        Concurrently retrieves customer history AND checks inventory/stock levels for a request.
        Always prefer this over calling customer_relationship_tool and inventory_tool separately.
        Args:
            request (str): The customer's request text.
        """
        # Wrap both agents with retry before passing to the async runner
        history_fn = _with_retry(agents["customer_relationship"], "customer_relationship_agent")
        inventory_fn = _with_retry(agents["inventory"], "inventory_agent")
        history, inventory = asyncio.run(
            _gather_context(history_fn, inventory_fn, request)
        )
        return f"=== CUSTOMER HISTORY ===\n{history}\n\n=== INVENTORY & DELIVERY ===\n{inventory}"

    @tool
    def customer_relationship_tool(request: str) -> str:
        """
        Retrieves essential historical context for a customer request.
        Args:
            request (str): The customer's request text.
        """
        return _with_retry(agents["customer_relationship"], "customer_relationship_agent")(request)

    @tool
    def inventory_tool(request: str) -> str:
        """
        Checks stock levels and delivery timelines for requested items.
        Args:
            request (str): A description of the item and date to check.
        """
        return _with_retry(agents["inventory"], "inventory_agent")(request)

    @tool
    def quotation_tool(request: str) -> str:
        """
        Generates a price quote for one or more items.
        Args:
            request (str): A description of the items and quantities to quote.
        """
        return _with_retry(agents["quotation"], "quotation_agent")(request)

    @tool
    def sales_tool(request: str) -> str:
        """
        Finalizes a confirmed sale and records the transaction.
        Args:
            request (str): A description of the order to fulfill including price.
        """
        return _with_retry(agents["sales"], "sales_agent")(request)

    @tool
    def parse_customer_request_tool(request: str) -> List[Tuple[str, int]]:
        """
        Parses a raw customer request string into a list of (item_name, quantity) tuples.
        Args:
            request (str): The raw customer request text.
        """
        return parse_customer_request(request)

    return [
        gather_context_tool,
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
    """Master orchestrator that coordinates all specialised sub-agents to handle
    customer requests end-to-end.

    Inherits from smolagents.ToolCallingAgent so it can invoke any registered tool
    via LLM-driven function calling. The system prompt instructs it to:
        1. Use gather_context_tool first (parallel history + inventory).
        2. Use quotation_tool to price the confirmed items.
        3. Use sales_tool to commit the transaction if the customer accepts.

    Args:
        model: A smolagents-compatible LLM model instance.
        tools: List of tool objects returned by create_orchestrator_tools().
    """

    def __init__(self, model, tools: list):
        super().__init__(
            name="orchestrator_agent",
            description=(
                "You are the master orchestrator of a sales team. Process customer requests and provide final outcomes. "
                "Always start with gather_context_tool to fetch history and inventory simultaneously in one step. "
                "Then use quotation_tool to price the order, and sales_tool to finalize confirmed sales."
            ),
            tools=tools,
            model=model,
        )
