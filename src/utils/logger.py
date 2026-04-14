"""
logger.py
=========
Logging and terminal display utilities for the Munder Difflin pipeline.

Classes:
    BatchStatusLogger  — prints structured progress lines for each batch request
    TerminalAnimator   — renders a live-updating stage dashboard in the terminal
    AgentFailureLogger — appends structured failure records to a JSONL file
"""

import json
import os
import time
from datetime import datetime


class BatchStatusLogger:
    """Logs progress messages for a single quote request during batch processing.

    Prints a header when the request starts, a timestamped line for each pipeline
    stage update, and a footer with the final agent response when complete.

    Attributes:
        request_id: Integer ID of the current batch request.
        job: Customer's job title / organisation type.
        event: Event type the customer is purchasing supplies for.
    """

    def __init__(self, request_id: int, job: str, event: str):
        """Prints the request header immediately on construction.

        Args:
            request_id: Integer ID used to identify this request in logs.
            job: Customer's job/organisation description.
            event: Event type context (e.g. "Spring Festival").
        """
        self.request_id = request_id
        self.job = job
        self.event = event
        print(f"\n===== Request #{self.request_id}: Starting Workflow =====")
        print(f"Context: {self.job} organizing {self.event}")

    def update(self, message: str) -> None:
        """Prints an intermediate pipeline stage update.

        Args:
            message: Human-readable description of the current pipeline stage.
        """
        print(f"  [Request #{self.request_id}] -> {message}")

    def finalize(self, final_response: str) -> None:
        """Prints the final agent response and closes the request block.

        Args:
            final_response: The orchestrator's final customer-facing response string.
        """
        print(f"  [Request #{self.request_id}] => FINAL RESPONSE: {final_response}")
        print(f"===== Request #{self.request_id}: Workflow Complete =====")


class TerminalAnimator:
    """Renders a live-updating pipeline stage dashboard that redraws the terminal.

    Tracks the status of each pipeline stage (CUSTOMER REQUEST → SALE FINALIZED)
    and redraws the full board on every update call, giving a progress-monitor feel.

    Class Attributes:
        STAGES: Ordered list of pipeline stage names shown in the dashboard.
    """

    STAGES = [
        "CUSTOMER REQUEST",
        "HISTORY CHECK",
        "INVENTORY CHECK",
        "DELIVERY TIMELINE",
        "QUOTE",
        "SALE FINALIZED",
    ]

    def __init__(self):
        """Initialises all stage statuses to "Pending..."."""
        self.statuses = {key: "Pending..." for key in self.STAGES}

    def update(self, key: str, message: str, delay: float = 1.0) -> None:
        """Updates a stage status and redraws the full dashboard.

        Args:
            key: One of the STAGES strings to update.
            message: New status message to display for that stage.
            delay: Seconds to sleep after drawing, allowing the user to read it.
        """
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

    def finalize(self, final_response: str) -> None:
        """Prints the final customer-facing response after all stages complete.

        Args:
            final_response: The orchestrator's final response string.
        """
        print("\n====== FINAL CUSTOMER-FACING RESPONSE ======")
        print(final_response)
        print("=" * 45)


class AgentFailureLogger:
    """Appends structured agent failure records to a JSONL file for diagnostics.

    Each log entry is a JSON object on its own line containing the timestamp,
    agent name, request ID, attempt number, and full error details. The file
    is created (including parent directories) automatically if it does not exist.

    The JSONL file is consumed by the NiceGUI dashboard to display a live
    failure log panel.

    Attributes:
        log_path: Absolute or relative path to the output JSONL file.
    """

    def __init__(self, log_path: str = "data/output/agent_failures.jsonl"):
        """Args:
            log_path: Path to the JSONL failure log file. Parent directories
                      are created automatically. Default "data/output/agent_failures.jsonl".
        """
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(self, agent_name: str, request_id: int, attempt: int, error: Exception) -> None:
        """Appends one failure record to the JSONL file and prints a summary line.

        Args:
            agent_name: Name of the agent that raised the exception.
            request_id: Batch request ID the agent was processing.
            attempt: Which retry attempt this failure occurred on (1-indexed).
            error: The exception instance that was caught.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "request_id": request_id,
            "attempt": attempt,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(
            f"[FAILURE LOG] agent={entry['agent']} | request={request_id} "
            f"| attempt={attempt} | {entry['error_type']}: {entry['error_message']}"
        )
