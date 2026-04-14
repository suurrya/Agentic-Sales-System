import os
import time
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from smolagents import OpenAIServerModel

from src.database.database import db_engine, init_database, generate_financial_report
from src.utils.parsers import (
    parse_customer_request,
    parse_price_from_quote,
    parse_stock_level_from_response,
)
from src.utils.logger import BatchStatusLogger
from src.agents.customer import CustomerAgent
from src.agents.specialized import create_specialized_agents
from src.agents.orchestrator import BestOrchestrator, create_orchestrator_tools


def run_test_scenarios(engine, model):
    print("Initializing Database...")
    init_database(engine)
    try:
        quote_requests_sample = pd.read_csv("data/input/quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return

    agents = create_specialized_agents(model)
    orchestrator_tools = create_orchestrator_tools(agents)
    orchestrator = BestOrchestrator(model, orchestrator_tools)

    reports = []
    oltp_log = []

    for idx, row in quote_requests_sample.iterrows():
        request_id = idx + 1
        request_date = row["request_date"].strftime("%Y-%m-%d")
        logger = BatchStatusLogger(request_id, row["job"], row["event"])
        customer = CustomerAgent(row)
        initial_request = customer.get_initial_request(request_date)

        logger.update(f"Initial Request: {initial_request}")

        # Phase 1: History check
        history_response = orchestrator(
            f"First, get the customer history for this request: {initial_request}"
        )
        logger.update("History Analysis Complete.")

        # Phase 2: Inventory check
        parsed_items = parse_customer_request(initial_request)
        is_out_of_stock, final_response, corrected_items = False, "", []
        quoted_price = 0.0

        if not parsed_items:
            final_response = "Apologies, I could not understand the items in your request."
        else:
            for item_name, quantity in parsed_items:
                stock_response = orchestrator(
                    f"Use your inventory_tool to check the stock for item: '{item_name}' as of {request_date}"
                )
                stock_level = parse_stock_level_from_response(stock_response)

                if stock_level < quantity:
                    similar_item_response = orchestrator(
                        f"Item '{item_name}' is out of stock ({stock_level} available). Find a similar item in inventory."
                    )
                    corrected_item_name = (
                        similar_item_response.strip()
                        if len(similar_item_response.split()) < 5
                        else ""
                    )

                    if corrected_item_name:
                        stock_response = orchestrator(
                            f"Check stock for the suggested replacement '{corrected_item_name}' as of {request_date}"
                        )
                        stock_level = parse_stock_level_from_response(stock_response)
                        if stock_level >= quantity:
                            item_name = corrected_item_name
                        else:
                            is_out_of_stock = True
                            final_response = (
                                f"Apologies, but '{item_name}' and its replacement are out of stock."
                            )
                            break
                    else:
                        is_out_of_stock = True
                        final_response = f"Apologies, but '{item_name}' is not in stock."
                        break
                corrected_items.append((item_name, quantity))

            if not is_out_of_stock:
                # Phase 3: Quote generation
                quote_request_text = " and ".join(
                    [f"{qty} of '{name}'" for name, qty in corrected_items]
                )
                quote_response = orchestrator(
                    f"All items are in stock. Generate a full price quote for: {quote_request_text}"
                )
                quoted_price = parse_price_from_quote(quote_response)

                # Phase 4: Customer decision and fulfillment
                if customer.evaluate_response(quoted_price) == "yes" and quoted_price > 0:
                    fulfillment_response = orchestrator(
                        f"Customer approved the price of ${quoted_price:.2f}. "
                        f"Use sales_tool to fulfill the order for {quote_request_text} at this price on {request_date}."
                    )
                    final_response = f"Sale finalized: {fulfillment_response}"
                else:
                    final_response = f"The customer rejected the price of ${quoted_price:.2f}."

        logger.finalize(final_response)

        # OLAP / OLTP reporting
        report = generate_financial_report(engine, request_date)
        reports.append({
            "request_id": request_id,
            "request_date": request_date,
            "cash_balance": report["cash_balance"],
            "inventory_value": report["inventory_value"],
            "response": final_response,
        })

        oltp_log.append({
            "transaction_id": f"txn_{request_id}_{int(time.time() * 1000)}",
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "customer_type": row["job"],
            "event": row["event"],
            "is_fulfilled": "Sale finalized" in final_response,
            "items_checked": len(parsed_items) if parsed_items else 0,
            "items_fulfilled": len(corrected_items) if "Sale finalized" in final_response else 0,
            "total_value": quoted_price if "Sale finalized" in final_response else 0.0,
        })

    pd.DataFrame(reports).to_csv("data/output/olap_database.csv", index=False)
    pd.DataFrame(oltp_log).to_csv("data/output/oltp_database.csv", index=False)

    return reports, oltp_log


if __name__ == "__main__":
    load_dotenv()
    model = OpenAIServerModel(
        model_id="gemma-7b",
        api_base="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY"),
    )

    db_path = "db/munder_difflin.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    init_database(db_engine)

    print("\n--- Generating test data (50 items) ---")

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
    run_test_scenarios(db_engine, model)
    print("\n--- Batch processing complete. Results saved to data/output/ ---")
