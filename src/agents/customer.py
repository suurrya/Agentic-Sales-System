"""
customer.py
===========
Simulates the customer side of a sales negotiation.

CustomerAgent wraps a customer's request data and budget into an object that can
either respond with a simple threshold check (no model) or engage in a real LLM
negotiation loop (when a model is provided).

LLM negotiation behaviour:
- Within budget          → accepts immediately (no LLM call needed)
- 0–20% over budget      → counter-offers (asks for discount / reduced qty / later delivery)
- > 20% over budget      → politely declines with budget stated
"""

import pandas as pd
from smolagents import ToolCallingAgent

from src.agents.prompts import CUSTOMER_NEGOTIATION_PROMPT


class CustomerAgent:
    """Simulates a customer's decision-making during the sales negotiation.

    When a model is supplied, over-budget quotes trigger a real LLM negotiation
    loop — the agent can counter-offer, request discounts, or decline with reasons.
    Without a model it falls back to a simple budget threshold check, which is
    useful for fast local testing without API calls.

    Attributes:
        request_text: The raw customer request string from the CSV.
        is_non_profit: True if the customer's job field contains "non-profit".
        budget: Spending limit in USD — $300 for non-profits, $150 otherwise.
        negotiation_strategy: "flexible_timeline" for non-profits, "strict_budget" otherwise.
    """

    def __init__(self, request_data: pd.Series, model=None):
        """Initialises the customer from a row of the quote_requests DataFrame.

        Args:
            request_data: A pandas Series with at least "request" and "job" fields.
            model: Optional smolagents-compatible LLM. If provided, over-budget quotes
                   are handled by an LLM agent rather than a hardcoded string.
        """
        self.request_text = request_data["request"]
        self.is_non_profit = "non-profit" in request_data["job"].lower()
        self.budget = 300 if self.is_non_profit else 150
        self.negotiation_strategy = "flexible_timeline" if self.is_non_profit else "strict_budget"

        # Only instantiate the LLM agent if a model was provided
        self._agent = None
        if model is not None:
            self._agent = ToolCallingAgent(
                name="customer_agent",
                description=CUSTOMER_NEGOTIATION_PROMPT.format(
                    budget=self.budget,
                    strategy=self.negotiation_strategy,
                ),
                tools=[],
                model=model,
            )

    def get_initial_request(self, date: str) -> str:
        """Formats the customer's request with the order date appended.

        Args:
            date: ISO-format date string representing when the request was submitted.

        Returns:
            The request text with the date appended in parentheses.
        """
        return f"{self.request_text} (Date of request: {date})"

    def evaluate_response(self, true_total_price: float, quote_text: str = "") -> str:
        """Evaluates the quoted price against the customer's budget and responds.

        If the price is within budget, returns "yes" immediately without any LLM call.
        If over budget and a model is available, delegates to the LLM negotiation agent.
        If over budget and no model is available, returns the hardcoded fallback string.

        Args:
            true_total_price: The total quoted price in USD.
            quote_text: Optional full quote explanation for LLM context. Default "".

        Returns:
            "yes" if accepted, an LLM-generated counter-offer or decline string otherwise.
        """
        if 0 < true_total_price <= self.budget:
            return "yes"
        if self._agent is not None:
            overage_pct = (true_total_price - self.budget) / self.budget * 100
            prompt = (
                f"The sales agent quoted ${true_total_price:.2f} for your order "
                f"({overage_pct:.0f}% over your ${self.budget:.2f} budget). "
                f"Quote details: {quote_text or 'no details provided'}. "
                "Respond as the customer."
            )
            return self._agent.run(prompt)
        return "no, that is too expensive"
