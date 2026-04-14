import pandas as pd


class CustomerAgent:
    """Simulates a customer's decision-making during the sales negotiation."""

    def __init__(self, request_data: pd.Series):
        self.request_text = request_data["request"]
        self.is_non_profit = "non-profit" in request_data["job"].lower()
        self.budget = 300 if self.is_non_profit else 150
        self.negotiation_strategy = "flexible_timeline" if self.is_non_profit else "strict_budget"

    def get_initial_request(self, date: str) -> str:
        return f"{self.request_text} (Date of request: {date})"

    def evaluate_response(self, true_total_price: float) -> str:
        if 0 < true_total_price <= self.budget:
            return "yes"
        return "no, that is too expensive"
