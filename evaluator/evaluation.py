"""
evaluation.py
=============
Runs the PaperTrail Co. agentic sales pipeline against 50 generated test cases.

Run from the project root:

    python evaluator/evaluation.py
    python evaluator/evaluation.py --limit 10   # process only first 10 requests

What this does
--------------
  1. Generates 50 synthetic customer quote requests
  2. Runs each through the full pipeline concurrently (up to 5 at once)
  3. Logs per-step latency and outcomes to data/output/test_results_log.txt

After this completes, run evaluator/evaluator.py to get a full performance report.
"""

import os
import sys

# Allow running from the project root OR from inside evaluator/
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_here, ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import argparse
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

from src.utils.model_wrapper import ResilientOpenAIModel  # also installs json-repair patch

from src.database.database import db_engine, init_database, generate_financial_report
from src.utils.parsers import (
    parse_customer_request,
    parse_price_from_quote,
    llm_parse_request,
)
from src.utils.logger import BatchStatusLogger, PipelineLogger
from src.agents.customer import CustomerAgent
from src.agents.specialized import create_specialized_agents
from src.agents.orchestrator import _with_retry
from src.tools.inventory_tools import check_inventory_tool, find_similar_inventory_item_tool

# At most this many requests run concurrently — guards against API rate limits.
MAX_CONCURRENT_REQUESTS = 5


async def _run_in_thread(fn, *args):
    """Dispatch a blocking synchronous call into the default thread pool so the
    event loop stays free to schedule other coroutines while it waits."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def _check_item_stock(item_name: str, quantity: int, request_date: str) -> tuple:
    """Resolve the canonical catalogue name for an item, then check its stock level.

    Calls find_similar_inventory_item_tool and check_inventory_tool directly —
    both are pure database queries with no LLM round-trip, making each check
    ~100x faster than routing through the inventory_agent.

    The catalogue lookup is always performed first so that casing differences
    between the parser output (e.g. "banner paper") and the DB record
    ("Banner paper") are resolved before the stock query, preventing false
    zero-stock results from case-sensitive SQL matching.

    Returns:
        (resolved_name, stock)  where resolved_name is None when no item with
        sufficient stock could be found.
    """
    loop = asyncio.get_running_loop()

    # Step 1: resolve the exact catalogue name (handles case, partial names, etc.)
    catalog_name = await loop.run_in_executor(
        None, lambda: find_similar_inventory_item_tool(search_term=item_name)
    )
    resolved = catalog_name if catalog_name else item_name

    # Step 2: single stock check using the canonical DB name
    stock = await loop.run_in_executor(
        None, lambda: check_inventory_tool(item_name=resolved, as_of_date=request_date)
    )
    if stock >= quantity:
        return resolved, stock

    return None, stock


async def _process_request(model, engine, row, request_id, latency_logger, semaphore):
    """Handle the full sales pipeline for a single customer request.

    A fresh set of agents and orchestrator is created for every request.
    smolagents resets self.memory at the start of each run(), so a shared
    instance is NOT safe to call from concurrent threads — per-request
    instantiation is the correct fix.  The model object is stateless and
    shared safely across all coroutines.
    """
    async with semaphore:
        # ── Per-request agent instantiation (lightweight — no API calls) ─────
        # Each specialized agent is called directly — bypassing the orchestrator
        # routing layer eliminates one extra LLM call per operation.
        agents = create_specialized_agents(model)

        request_date = row["request_date"].strftime("%Y-%m-%d")
        logger = BatchStatusLogger(request_id, row["job"], row["event"])
        customer = CustomerAgent(row, model)
        initial_request = customer.get_initial_request(request_date)
        logger.update(f"Initial Request: {initial_request}")

        # Use .run() directly — calling agents["quotation"](...) invokes __call__(),
        # which wraps the task in smolagents' managed_agent_prompt (verbose 3-section
        # final_answer format). .run() skips that wrapper and uses our system prompt.
        quotation_agent = _with_retry(agents["quotation"].run, "quotation_agent", request_id)
        sales_agent     = _with_retry(agents["sales"].run,    "sales_agent",     request_id)

        # ── Phase 1: Parallel inventory checks (direct DB calls — no LLM) ────
        # check_inventory_tool and find_similar_inventory_item_tool are pure SQL
        # queries.  Calling them directly eliminates the LLM round-trip that was
        # adding 3–14 s per item, and asyncio.gather checks all items at once.
        parsed_items = parse_customer_request(initial_request)
        # LLM fallback — only fires when the regex parser returns nothing
        if not parsed_items:
            print(f"  [Request #{request_id}] Regex parse returned nothing — falling back to LLM parser")
            parsed_items = await _run_in_thread(llm_parse_request, initial_request, agents["parser"])

        is_out_of_stock, final_response, corrected_items = False, "", []
        quoted_price = 0.0

        if not parsed_items:
            final_response = "Apologies, I could not understand the items in your request."
        else:
            latency_logger.start(request_id, "INVENTORY CHECK")
            check_results = await asyncio.gather(
                *[_check_item_stock(name, qty, request_date) for name, qty in parsed_items],
                return_exceptions=True,
            )
            latency_logger.end(request_id, "INVENTORY CHECK")

            for (item_name, quantity), result in zip(parsed_items, check_results):
                if isinstance(result, Exception):
                    resolved_name, stock_level = None, 0
                else:
                    resolved_name, stock_level = result
                if resolved_name is None:
                    is_out_of_stock = True
                    final_response = (
                        f"Apologies, but '{item_name}' has insufficient stock "
                        f"({stock_level} available, {quantity} needed)."
                    )
                    break
                corrected_items.append((resolved_name, quantity))

            if not is_out_of_stock:
                # ── Phase 3: Quote generation ─────────────────────────────────

                quote_request_text = " and ".join(
                    [f"{qty} of '{name}'" for name, qty in corrected_items]
                )
                latency_logger.start(request_id, "QUOTE")
                try:
                    quote_response = await _run_in_thread(
                        quotation_agent,
                        f"Generate a full price quote for: {quote_request_text}",
                    )
                except Exception:
                    quote_response = ""
                latency_logger.end(request_id, "QUOTE")
                quoted_price = parse_price_from_quote(quote_response)

                # ── Phase 4: Customer decision + fulfillment ──────────────────
                customer_decision = customer.evaluate_response(quoted_price, quote_response)
                if "yes" in customer_decision.lower() and quoted_price > 0:
                    # Snapshot max transaction ID before the agent runs.
                    # This is the DB-level verification recommended by CLAUDE.md:
                    # the source of truth is whether rows were actually inserted,
                    # not what the agent's final_answer text claims.
                    loop = asyncio.get_running_loop()
                    pre_max_id = await loop.run_in_executor(
                        None,
                        lambda: int(pd.read_sql(
                            "SELECT COALESCE(MAX(id), 0) as max_id FROM transactions",
                            engine,
                        ).iloc[0]["max_id"]),
                    )

                    latency_logger.start(request_id, "FULFILLMENT")
                    try:
                        fulfillment_response = await _run_in_thread(
                            sales_agent,
                            f"Fulfill the order for {quote_request_text} at ${quoted_price:.2f} on {request_date}.",
                        )
                    except Exception as e:
                        fulfillment_response = f"Fulfillment failed: {e}"
                    latency_logger.end(request_id, "FULFILLMENT")

                    # DB verification: count new sales rows written since pre_max_id.
                    # If zero → agent never called fulfill_order_tool (hallucination).
                    new_txn_count = await loop.run_in_executor(
                        None,
                        lambda: int(pd.read_sql(
                            "SELECT COUNT(*) as cnt FROM transactions "
                            "WHERE id > :max_id AND transaction_type = 'sales'",
                            engine,
                            params={"max_id": pre_max_id},
                        ).iloc[0]["cnt"]),
                    )
                    if new_txn_count == 0:
                        print(f"[HALLUCINATION DETECTED] Request #{request_id}: "
                              f"sales agent claimed fulfillment but no DB rows were written.")
                        final_response = "Fulfillment failed: sales agent did not record the transaction (hallucination detected)."
                    else:
                        final_response = f"Sale finalized: {fulfillment_response}"
                else:
                    final_response = f"The customer rejected the price of ${quoted_price:.2f}."

        logger.finalize(final_response)

        # Derive outcome and reason from the pipeline result for the log
        if not parsed_items:
            outcome = "Parse failure"
            reason = "Could not understand items in request"
        elif is_out_of_stock:
            outcome = "Insufficient stock"
            # Extract the item detail from the already-built final_response
            reason = final_response.replace("Apologies, but ", "").rstrip(".")
        elif "Sale finalized" in final_response:
            outcome = f"Sale finalized at ${quoted_price:.2f}"
            items_str = ", ".join(f"{qty}x {name}" for name, qty in corrected_items)
            reason = f"{items_str} — all in stock, within budget"
        elif "Fulfillment failed" in final_response:
            outcome = f"Fulfillment failed at ${quoted_price:.2f}"
            reason = "Customer accepted but sales agent did not record the transaction"
        elif quoted_price > 0:
            outcome = f"Customer rejected at ${quoted_price:.2f}"
            reason = "Quote exceeded customer budget"
        else:
            outcome = "Quote generation failed"
            reason = "No valid price extracted from quotation agent"

        latency_logger.finalise(request_id, outcome=outcome, reason=reason)


async def run_test_scenarios(engine, model, limit: int = None):
    print("Initializing Database...")
    init_database(engine)
    try:
        quote_requests_sample = pd.read_csv("data/input/quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
        if limit is not None:
            quote_requests_sample = quote_requests_sample.head(limit)
            print(f"(--limit {limit}: processing first {len(quote_requests_sample)} requests)")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return

    latency_logger = PipelineLogger("data/output/test_results_log.txt")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    # Dispatch all requests concurrently; semaphore caps active workers at
    # MAX_CONCURRENT_REQUESTS so we don't flood the NVIDIA API.
    tasks = [
        _process_request(model, engine, row, idx + 1, latency_logger, semaphore)
        for idx, row in quote_requests_sample.iterrows()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    errors = 0
    for r in results:
        if isinstance(r, Exception):
            print(f"[ERROR] A request task raised an unhandled exception: {r}")
            errors += 1

    if errors:
        print(f"[WARN] {errors} request(s) raised unhandled exceptions.")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the PaperTrail Co. Agentic Sales pipeline.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process only the first N requests (default: all 50).",
    )
    args = parser.parse_args()

    load_dotenv()
    model = ResilientOpenAIModel(
        model_id="meta/llama-3.3-70b-instruct",
        api_base="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY"),
        # temperature=0.0 is the default in ResilientOpenAIModel — forces the
        # model to always pick the highest-probability (correct) JSON token.
        #
        # timeout=30: cap each individual API call at 30 seconds.  Without this,
        # a throttled NVIDIA call can silently hang for 60-70 s while holding
        # the threading.Semaphore slot — starving every other agent.  After 30 s
        # the OpenAI SDK raises APITimeoutError, the semaphore is released, and
        # ResilientOpenAIModel's retry loop treats it the same as an empty response.
        client_kwargs={"timeout": 30},
    )

    db_path = "db/munder_difflin.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    init_database(db_engine)

    print("\n--- PaperTrail Co. | Generating test data (50 items) ---")

    base_requests = [
        (
            "I need 500 sheets of A4 paper, 200 sheets of construction paper, and 50 paper party bags for an upcoming school event.",
            "School Admin", "Spring Festival",
        ),
        (
            "Hello, please provide a quote for 1000 flyers, 20 large poster paper (24x36 inches), and 5 rolls of banner paper (36-inch width) for our marketing campaign.",
            "Marketing Agency", "Product Launch",
        ),
        (
            "We are a non-profit organizing a charity gala. Could we order 300 invitation cards, 300 envelopes, and 50 table covers?",
            "Non-profit Coordinator", "Charity Gala",
        ),
        (
            "Hi, I am looking to purchase 2000 disposable cups, 2000 paper plates, and 4000 paper napkins for our regional food festival next month.",
            "Event Planner", "Food Festival",
        ),
        (
            "Our corporate office needs 100 presentation folders, 200 notepads, and 500 sticky notes.",
            "Corporate Buyer", "Quarterly Conference",
        ),
    ]

    generated_rows = []
    start_date = datetime(2026, 1, 10)
    for i in range(50):
        req_date = (start_date + timedelta(days=i)).strftime("%m/%d/%y")
        base_req = base_requests[i % 5]
        generated_rows.append(f'{req_date},"{base_req[0]}","{base_req[1]}","{base_req[2]}"')

    with open("data/input/quote_requests_sample.csv", "w") as f:
        f.write("request_date,request,job,event\n")
        for row in generated_rows:
            f.write(row + "\n")

    print("Generated 50 test requests in data/input/quote_requests_sample.csv")

    print("\n--- Starting BATCH processing ---")
    asyncio.run(run_test_scenarios(db_engine, model, limit=args.limit))
    print("\n--- Batch processing complete. Results saved to data/output/ ---")
    print("--- Run `python evaluator/evaluator.py` to evaluate the results ---")
