"""
ui/app.py
=========
PaperTrail Co. — four-page NiceGUI web application.

Pages
-----
  /            Landing page — email selection, "Begin Session" → session start
  /portal      Customer request portal — submit an order, watch it process live
  /live        OLTP live feed — transactions auto-refresh every 5 s from the DB
  /analytics   OLAP analytics — charts from batch CSV output + live DB aggregates

Run
---
    python ui/app.py

Or add the --reload flag during development:
    python ui/app.py --reload
"""

import asyncio
import os
import sys
import threading
import time
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

# ── Path: app.py lives in ui/; project root must be on sys.path ───────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

from nicegui import app, ui

from src.database.database import db_engine, generate_financial_report
from src.database.customer_db import (
    customer_engine,
    get_users_with_completed_transactions,
    get_user_by_email,
)
from src.utils.model_wrapper import ResilientOpenAIModel  # also installs json patches
from src.utils.parsers import parse_customer_request, parse_price_from_quote, llm_parse_request
from src.utils.logger import PipelineLogger
from src.agents.specialized import create_specialized_agents
from src.agents.orchestrator import _with_retry
from src.tools.inventory_tools import check_inventory_tool, find_similar_inventory_item_tool

# ── Shared model (one instance, shared across all requests) ───────────────────
_model = ResilientOpenAIModel(
    model_id="meta/llama-3.3-70b-instruct",
    api_base="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY"),
    client_kwargs={"timeout": 30},
)

OLAP_PATH = "data/output/olap_database.csv"
OLTP_PATH = "data/output/oltp_database.csv"

# OLTP resets on every app.py startup (fresh session log).
# OLAP is append-only and persists across restarts and resets.
os.makedirs("data/output", exist_ok=True)
open(OLTP_PATH, "w").close()  # clear OLTP on startup

# Persistent logger for web requests — append=True so it never clears on restart
# and each request adds on to the same file across sessions.
_web_logger = PipelineLogger("data/output/pipeline_log.txt", append=True)

# Thread-safe CSV helpers — OLTP and OLAP are append-only from app.py only.
# evaluator/evaluation.py (batch test cases) no longer writes to these files.
_csv_lock = threading.Lock()


def _append_row(path: str, row: dict) -> None:
    """Append one row to a CSV file. Creates the file with headers on first write.
    Thread-safe via _csv_lock so concurrent web requests don't corrupt the file.
    """
    with _csv_lock:
        df = pd.DataFrame([row])
        if os.path.exists(path) and os.path.getsize(path) > 0:
            df.to_csv(path, mode="a", header=False, index=False)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            df.to_csv(path, index=False)

BRAND_COLOR = "bg-teal-800"
BRAND_ACCENT = "text-teal-700"


# ── Shared UI components ───────────────────────────────────────────────────────

def nav_bar():
    with ui.header().classes(f"{BRAND_COLOR} text-white px-6 py-3 flex items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("receipt_long").classes("text-2xl")
            with ui.column().classes("gap-0"):
                ui.label("PaperTrail Co.").classes("text-xl font-bold leading-tight")
                ui.label("Every sheet. Every deal. Tracked.").classes(
                    "text-xs text-teal-300 leading-tight"
                )
        with ui.row().classes("gap-6"):
            ui.link("Order", "/portal").classes("text-white hover:text-teal-200 font-medium text-sm")



# ── Pipeline helper (mirrors evaluator/evaluation.py _check_item_stock) ───────

async def _check_item_stock(item_name: str, quantity: int, request_date: str) -> tuple:
    loop = asyncio.get_running_loop()
    catalog_name = await loop.run_in_executor(
        None, lambda: find_similar_inventory_item_tool(search_term=item_name)
    )
    resolved = catalog_name if catalog_name else item_name
    stock = await loop.run_in_executor(
        None, lambda: check_inventory_tool(item_name=resolved, as_of_date=request_date)
    )
    return (resolved, stock) if stock >= quantity else (None, stock)


async def run_web_pipeline(
    request_text: str,
    job_type: str,
    event: str,
    on_status,        # sync callable(str) — updates the UI status label
    on_quote_ready,   # async callable(price, quote_text) -> bool — shows quote to user, returns True=accept
):
    """Run the full sales pipeline for one web-submitted order.

    Follows the Customer Order Fulfillment chart:
      Phase 1 — Inventory check  (direct SQL, no LLM)
      Phase 2 — Quote generation (QuotationAgent)
      Phase 3 — Customer approval (real user via UI — not a simulated agent)
      Phase 4 — Fulfillment      (SalesAgent, only on acceptance)

    Returns (final_message: str, success: bool).
    Writes one row to OLTP and one row to OLAP at every exit.
    """
    request_date = datetime.now().strftime("%Y-%m-%d")
    loop = asyncio.get_running_loop()

    agents = create_specialized_agents(_model)
    # Use the user's request text directly — no LLM customer simulation needed
    initial_request = request_text

    quotation_agent = _with_retry(agents["quotation"].run, "quotation_agent", 0)
    sales_agent     = _with_retry(agents["sales"].run,     "sales_agent",     0)

    req_id = int(time.time() * 1000)
    items_checked  = 0
    items_fulfilled = 0
    quoted_price   = 0.0
    corrected_items = []

    async def _commit(msg: str, success: bool, outcome: str, reason: str) -> tuple:
        _web_logger.finalise(req_id, outcome=outcome, reason=reason)
        cash = await loop.run_in_executor(
            None,
            lambda: float(pd.read_sql(
                "SELECT COALESCE(SUM(CASE WHEN transaction_type='sales' THEN price "
                "ELSE -price END), 0) AS cash FROM transactions",
                db_engine,
            ).iloc[0]["cash"]),
        )
        inv_value = 0.0
        if success:
            report = await loop.run_in_executor(
                None, generate_financial_report, db_engine, request_date
            )
            inv_value = report["inventory_value"]
        await loop.run_in_executor(None, _append_row, OLTP_PATH, {
            "transaction_id": f"web_{req_id}",
            "request_id":     req_id,
            "timestamp":      datetime.now().isoformat(),
            "customer_type":  job_type,
            "event":          event,
            "is_fulfilled":   success,
            "items_checked":  items_checked,
            "items_fulfilled": items_fulfilled if success else 0,
            "total_value":    quoted_price if success else 0.0,
        })
        await loop.run_in_executor(None, _append_row, OLAP_PATH, {
            "request_id":    req_id,
            "request_date":  request_date,
            "cash_balance":  cash,
            "inventory_value": inv_value,
            "response":      msg,
        })
        return msg, success

    # ── Phase 1: Parse ────────────────────────────────────────────────────────
    on_status("Parsing your request...")
    parsed_items = parse_customer_request(initial_request)
    if not parsed_items:
        on_status("Couldn't parse automatically — using AI to interpret your request...")
        parsed_items = await loop.run_in_executor(
            None, llm_parse_request, initial_request, agents["parser"]
        )
    if not parsed_items:
        msg = "Sorry, I couldn't understand the items in your request."
        on_status(msg)
        return await _commit(msg, False, "Parse failure", "Could not understand items in request")

    items_checked = len(parsed_items)

    # ── Phase 2: Inventory check (parallel direct DB calls — no LLM) ──────────
    on_status(f"Checking inventory for {items_checked} item(s)...")
    _web_logger.start(req_id, "INVENTORY CHECK")
    check_results = await asyncio.gather(
        *[_check_item_stock(name, qty, request_date) for name, qty in parsed_items],
        return_exceptions=True,
    )
    _web_logger.end(req_id, "INVENTORY CHECK")

    for (item_name, quantity), result in zip(parsed_items, check_results):
        resolved_name, stock_level = (None, 0) if isinstance(result, Exception) else result
        if resolved_name is None:
            msg = f"'{item_name}' has insufficient stock ({stock_level} available, {quantity} needed)."
            on_status(f"Out of stock: {msg}")
            return await _commit(
                msg, False, "Insufficient stock",
                f"'{item_name}' has insufficient stock ({stock_level} available, {quantity} needed)",
            )
        corrected_items.append((resolved_name, quantity))

    # ── Phase 3: Quote generation ─────────────────────────────────────────────
    quote_request_text = " and ".join(f"{qty} of '{name}'" for name, qty in corrected_items)
    on_status("All items in stock — generating price quote...")
    _web_logger.start(req_id, "QUOTE")
    try:
        quote_response = await loop.run_in_executor(
            None, quotation_agent,
            f"Generate a full price quote for: {quote_request_text}",
        )
    except Exception:
        quote_response = ""
    _web_logger.end(req_id, "QUOTE")

    quoted_price = parse_price_from_quote(quote_response)
    if quoted_price <= 0:
        msg = "Quote generation failed — could not extract a price."
        on_status(msg)
        return await _commit(msg, False, "Quote failure", "No valid price extracted")

    # ── Phase 4: Customer approval (real user decision via UI) ────────────────
    # Pipeline pauses here — on_quote_ready shows the quote card and waits for
    # the user to click Accept or Decline before returning True/False.
    items_summary = ", ".join(f"{qty}× {name}" for name, qty in corrected_items)
    on_status(f"Quote ready: ${quoted_price:.2f} — awaiting your decision...")
    accepted = await on_quote_ready(quoted_price, items_summary)

    if not accepted:
        msg = f"Order declined. You chose not to proceed at ${quoted_price:.2f}."
        on_status(msg)
        return await _commit(
            msg, False,
            f"Customer rejected at ${quoted_price:.2f}", "User declined the quote",
        )

    # ── Phase 5: Fulfillment (only reached on explicit user acceptance) ────────
    on_status(f"Quote accepted at ${quoted_price:.2f} — processing fulfillment...")
    pre_max_id = await loop.run_in_executor(
        None,
        lambda: int(pd.read_sql(
            "SELECT COALESCE(MAX(id), 0) as max_id FROM transactions", db_engine
        ).iloc[0]["max_id"]),
    )
    _web_logger.start(req_id, "FULFILLMENT")
    try:
        await loop.run_in_executor(
            None, sales_agent,
            f"Fulfill the order for {quote_request_text} at ${quoted_price:.2f} on {request_date}.",
        )
    except Exception as e:
        _web_logger.end(req_id, "FULFILLMENT")
        msg = f"Fulfillment error: {e}"
        on_status(msg)
        return await _commit(msg, False, "Fulfillment error", str(e))
    _web_logger.end(req_id, "FULFILLMENT")

    new_txn_count = await loop.run_in_executor(
        None,
        lambda: int(pd.read_sql(
            "SELECT COUNT(*) as cnt FROM transactions "
            "WHERE id > :max_id AND transaction_type = 'sales'",
            db_engine, params={"max_id": pre_max_id},
        ).iloc[0]["cnt"]),
    )
    if new_txn_count == 0:
        msg = "Fulfillment failed: agent did not record the transaction."
        on_status(msg)
        return await _commit(
            msg, False,
            f"Fulfillment failed at ${quoted_price:.2f}",
            "Agent did not record the transaction (hallucination detected)",
        )

    items_fulfilled = len(corrected_items)
    items_str = ", ".join(f"{qty}x {name}" for name, qty in corrected_items)
    msg = f"Sale finalized at ${quoted_price:.2f}!"
    on_status(msg)
    return await _commit(
        msg, True,
        f"Sale finalized at ${quoted_price:.2f}",
        f"{items_str} — all in stock, within budget",
    )


# ── Page 0: Landing / Email Selection (/) ────────────────────────────────────

@ui.page("/")
def landing_page():
    ui.page_title("PaperTrail Co. — Welcome")

    with ui.column().classes("min-h-screen w-full items-center justify-center bg-gray-50"):
        with ui.card().classes("w-full max-w-md shadow-xl p-8 gap-6"):
            # Header
            with ui.row().classes("items-center gap-3 mb-2"):
                ui.icon("receipt_long").classes("text-4xl text-teal-700")
                with ui.column().classes("gap-0"):
                    ui.label("PaperTrail Co.").classes("text-2xl font-bold text-gray-800")
                    ui.label("Every sheet. Every deal. Tracked.").classes(
                        "text-xs text-teal-600"
                    )

            ui.separator()

            ui.label("Select your account to begin").classes(
                "text-sm text-gray-500 text-center w-full"
            )

            # Populate dropdown from users with completed transactions
            users = get_users_with_completed_transactions(customer_engine)
            # Format: "email → Full Name (Company)" — parsed on Begin Session
            options = [
                f"{u['email']} → {u['full_name']} ({u['company']})"
                for u in users
            ]

            email_select = ui.select(
                label="Select User Email",
                options=options,
                value=None,
            ).props('placeholder="Please select your email"').classes("w-full")

            error_label = ui.label("").classes("text-red-500 text-sm hidden")

            def begin_session():
                if not email_select.value:
                    error_label.set_text("Please select an email to continue.")
                    error_label.classes(remove="hidden")
                    return

                # Extract email by splitting on the " → " delimiter
                email = email_select.value.split(" → ")[0].strip()
                user = get_user_by_email(email, customer_engine)

                if user is None:
                    error_label.set_text("User not found. Please try again.")
                    error_label.classes(remove="hidden")
                    return

                # Store user session — persists across page navigations
                app.storage.user.update({
                    "user_id":       user["user_id"],
                    "email":         user["email"],
                    "full_name":     user["full_name"],
                    "company":       user["company"],
                    "customer_type": user["customer_type"],
                })
                ui.navigate.to("/portal")

            ui.button("Begin Session", icon="login", on_click=begin_session).classes(
                "bg-teal-700 text-white w-full mt-2"
            )


# ── Page 1: Customer Order Portal (/portal) ───────────────────────────────────

@ui.page("/portal")
def order_page():
    # Redirect to landing if no session
    session = app.storage.user
    if not session.get("full_name"):
        ui.navigate.to("/")
        return

    nav_bar()
    ui.page_title("PaperTrail Co. — Place an Order")

    with ui.column().classes("w-full max-w-2xl mx-auto px-6 py-8 gap-5"):
        # ── Personalised welcome message ──────────────────────────────────────
        with ui.card().classes("w-full bg-teal-50 border border-teal-200 px-4 py-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("waving_hand").classes("text-teal-600 text-xl")
                ui.label(
                    f"Welcome back, {session['full_name']} "
                    f"from {session['company']}!"
                ).classes("text-teal-800 font-semibold text-sm")

        with ui.column().classes("gap-1"):
            ui.label("Place an Order").classes("text-2xl font-bold text-gray-800")
            ui.label(
                "Describe what you need. We'll check stock, quote a price, "
                "and process your order automatically."
            ).classes("text-gray-500 text-sm")

        with ui.card().classes("w-full shadow p-4"):
            with ui.column().classes("w-full gap-3"):
                job_select = ui.select(
                    label="Customer Type",
                    options=[
                        "Corporate Buyer",
                        "School Admin",
                        "Marketing Agency",
                        "Non-profit Coordinator",
                        "Event Planner",
                        "Other",
                    ],
                    value=session.get("customer_type", "Corporate Buyer"),
                ).classes("w-full")

                event_input = ui.input(
                    "Event / Purpose", placeholder="e.g. Annual Conference"
                ).classes("w-full")

                request_area = ui.textarea(
                    "What do you need?",
                    placeholder=(
                        "e.g. I need 200 A4 paper, 50 notepads, "
                        "and 100 presentation folders."
                    ),
                ).props("rows=4").classes("w-full")

                submit_btn = ui.button("Submit Order", icon="send").classes(
                    "bg-teal-700 text-white w-full mt-1"
                )

        # ── Status panel (hidden until submit) ───────────────────────────────
        EXPECTED_SECONDS = 120  # conservative estimate for one-item pipeline

        status_card = ui.card().classes("w-full shadow hidden")
        with status_card:
            with ui.row().classes("items-center gap-2 mb-2"):
                status_spinner = ui.spinner(size="sm")
                status_label = ui.label("Starting...").classes("text-sm text-gray-600")
            # Manual progress bar — avoids NiceGUI rendering the raw fraction as text
            with ui.element("div").classes("w-full bg-gray-200 rounded-full h-2"):
                progress_fill = ui.element("div").classes(
                    "bg-teal-600 h-2 rounded-full transition-all duration-500"
                ).style("width: 0%")
            with ui.row().classes("justify-between w-full mt-1"):
                elapsed_label = ui.label("0s elapsed").classes("text-xs text-gray-400")
                expected_label = ui.label(
                    f"~{EXPECTED_SECONDS}s expected"
                ).classes("text-xs text-gray-400")
            patience_label = ui.label("").classes(
                "text-amber-600 text-sm font-medium mt-1 hidden"
            )

        # ── Quote approval card (hidden until quote is ready) ────────────────
        quote_card = ui.card().classes("w-full shadow hidden border-2 border-blue-300 bg-blue-50")
        with quote_card:
            ui.label("Price Quote Ready").classes("text-base font-semibold text-blue-800 mb-1")
            quote_detail = ui.label("").classes("text-sm text-gray-600 mb-3")
            quote_price  = ui.label("").classes("text-3xl font-bold text-blue-700 mb-4")
            ui.label("Do you agree to this price?").classes("text-sm text-gray-700 font-medium")
            with ui.row().classes("gap-3 mt-2"):
                accept_btn  = ui.button("Accept Quote", icon="check_circle").classes(
                    "bg-green-600 text-white"
                )
                decline_btn = ui.button("Decline", icon="cancel").classes(
                    "bg-red-500 text-white"
                )

        result_card = ui.card().classes("w-full shadow hidden")
        with result_card:
            result_label = ui.label("").classes("text-base font-medium")

        async def submit():
            if not request_area.value.strip():
                ui.notify("Please describe what you need.", type="warning")
                return

            submit_btn.disable()
            status_card.classes(remove="hidden")
            quote_card.classes(add="hidden")
            result_card.classes(add="hidden")
            patience_label.classes(add="hidden")
            patience_label.set_text("")
            progress_fill.style("width: 0%")

            start_time = time.time()

            def update_status(msg: str):
                status_label.set_text(msg)

            def tick():
                elapsed = time.time() - start_time
                pct = min(elapsed / EXPECTED_SECONDS * 100, 100)
                progress_fill.style(f"width: {pct:.1f}%")
                elapsed_label.set_text(f"{int(elapsed)}s elapsed")
                if elapsed > EXPECTED_SECONDS:
                    patience_label.classes(remove="hidden")
                    patience_label.set_text(
                        "This is getting longer than expected — thank you for your patience."
                    )

            progress_timer = ui.timer(1.0, tick)

            # ── Quote approval: pause pipeline, ask the real user ─────────────
            # asyncio.Event lets run_web_pipeline await the user's button click.
            _decision_event = asyncio.Event()
            _user_accepted  = [False]

            async def on_quote_ready(price: float, items_summary: str) -> bool:
                """Show the quote card and suspend until the user clicks Accept or Decline."""
                quote_detail.set_text(items_summary)
                quote_price.set_text(f"${price:,.2f}")
                quote_card.classes(remove="hidden")
                progress_timer.cancel()           # pause the bar while user decides
                status_spinner.classes(add="hidden")
                _decision_event.clear()
                await _decision_event.wait()      # suspend until button click
                quote_card.classes(add="hidden")
                return _user_accepted[0]

            def on_accept():
                _user_accepted[0] = True
                _decision_event.set()
                status_spinner.classes(remove="hidden")  # resume spinner for fulfillment

            def on_decline():
                _user_accepted[0] = False
                _decision_event.set()

            accept_btn.on_click(on_accept)
            decline_btn.on_click(on_decline)

            try:
                final_msg, success = await run_web_pipeline(
                    request_text=request_area.value,
                    job_type=job_select.value,
                    event=event_input.value or "General Order",
                    on_status=update_status,
                    on_quote_ready=on_quote_ready,
                )
                progress_timer.cancel()
                progress_fill.style("width: 100%")
                status_spinner.classes(add="hidden")

                result_card.classes(remove="hidden")
                result_label.set_text(final_msg)
                if success:
                    result_card.classes(remove="bg-red-50 border-red-300 bg-amber-50 border-amber-300")
                    result_card.classes(add="bg-green-50 border border-green-300")
                    result_label.classes(remove="text-amber-800 text-red-800")
                    result_label.classes(add="text-green-800")
                    ui.notify("Order fulfilled!", type="positive")
                else:
                    result_card.classes(remove="bg-red-50 border-red-300 bg-green-50 border-green-300")
                    result_card.classes(add="bg-amber-50 border border-amber-300")
                    result_label.classes(remove="text-green-800 text-red-800")
                    result_label.classes(add="text-amber-800")
            except Exception as exc:
                progress_timer.cancel()
                progress_fill.style("width: 100%")
                status_spinner.classes(add="hidden")
                quote_card.classes(add="hidden")
                result_card.classes(remove="hidden")
                result_label.set_text(f"Error: {exc}")
                result_card.classes(add="bg-red-50 border border-red-300")
                ui.notify(f"Pipeline error: {exc}", type="negative")
            finally:
                submit_btn.enable()

        submit_btn.on_click(submit)


# ── Restricted routes — redirect customers to the order portal ────────────────

def _restricted_page(page_name: str):
    """Shown when a customer navigates to a manager-only URL."""
    ui.page_title("PaperTrail Co. — Access Restricted")
    with ui.column().classes("min-h-screen w-full items-center justify-center bg-gray-50"):
        with ui.card().classes("w-full max-w-md shadow-xl p-8 text-center gap-4"):
            ui.icon("lock").classes("text-5xl text-teal-700 mx-auto")
            ui.label("Manager Access Only").classes("text-xl font-bold text-gray-800")
            ui.label(
                f"The {page_name} page is restricted to managers. "
                "Please use the Manager Dashboard (port 8081)."
            ).classes("text-sm text-gray-500")
            ui.button("Back to Order Portal", icon="arrow_back",
                      on_click=lambda: ui.navigate.to("/portal")).classes(
                "bg-teal-700 text-white mt-2 w-full"
            )


@ui.page("/live")
def live_restricted():
    _restricted_page("Live Feed")


@ui.page("/analytics")
def analytics_restricted():
    _restricted_page("Analytics")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="PaperTrail Co.",
        port=8080,
        favicon="📄",
        dark=False,
        show=False,
        reconnect_timeout=600,       # keep the websocket alive for up to 10 min
        storage_secret="papertrail-co-secret-2026",  # required for app.storage.user
    )
