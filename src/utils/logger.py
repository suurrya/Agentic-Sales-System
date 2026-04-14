import os
import time


class BatchStatusLogger:
    """Logs progress for a single quote request in batch mode."""

    def __init__(self, request_id: int, job: str, event: str):
        self.request_id = request_id
        self.job = job
        self.event = event
        print(f"\n===== Request #{self.request_id}: Starting Workflow =====")
        print(f"Context: {self.job} organizing {self.event}")

    def update(self, message: str):
        print(f"  [Request #{self.request_id}] -> {message}")

    def finalize(self, final_response: str):
        print(f"  [Request #{self.request_id}] => FINAL RESPONSE: {final_response}")
        print(f"===== Request #{self.request_id}: Workflow Complete =====")


class TerminalAnimator:
    """Renders a live-updating status dashboard in the terminal."""

    STAGES = [
        "CUSTOMER REQUEST",
        "HISTORY CHECK",
        "INVENTORY CHECK",
        "DELIVERY TIMELINE",
        "QUOTE",
        "SALE FINALIZED",
    ]

    def __init__(self):
        self.statuses = {key: "Pending..." for key in self.STAGES}

    def update(self, key: str, message: str, delay: float = 1.0):
        if key in self.statuses:
            self.statuses[key] = message
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 45)
        print("===== Munder Difflin Agentic Workflow =====")
        print("=" * 45)
        for k in self.STAGES:
            print(f"  - {k:<20}: {self.statuses[k]}")
        print("-" * 45)
        time.sleep(delay)

    def finalize(self, final_response: str):
        print("\n====== FINAL CUSTOMER-FACING RESPONSE ======")
        print(final_response)
        print("=" * 45)
