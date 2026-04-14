# import pandas as pd
# import numpy as np
# import os
# import time
# from smolagents import ToolCallingAgent, tool, OpenAIServerModel
# from dotenv import load_dotenv
# import ast
# import re
# from sqlalchemy.sql import text
# from datetime import datetime, timedelta
# from typing import Dict, List, Union, Tuple
# from sqlalchemy import create_engine, Engine
# 
# # Create an SQLite database
# db_engine = create_engine("sqlite:///munder_difflin.db")
# 
# # List containing the different kinds of papers 
# paper_supplies = [
#     # Paper Types (priced per sheet unless specified)
#     {"item_name": "A4 paper",                         "category": "paper",        "unit_price": 0.05},
#     {"item_name": "Letter-sized paper",              "category": "paper",        "unit_price": 0.06},
#     {"item_name": "Cardstock",                        "category": "paper",        "unit_price": 0.15},
#     {"item_name": "Colored paper",                    "category": "paper",        "unit_price": 0.10},
#     {"item_name": "Glossy paper",                     "category": "paper",        "unit_price": 0.20},
#     {"item_name": "Matte paper",                      "category": "paper",        "unit_price": 0.18},
#     {"item_name": "Recycled paper",                   "category": "paper",        "unit_price": 0.08},
#     {"item_name": "Eco-friendly paper",               "category": "paper",        "unit_price": 0.12},
#     {"item_name": "Poster paper",                     "category": "paper",        "unit_price": 0.25},
#     {"item_name": "Banner paper",                     "category": "paper",        "unit_price": 0.30},
#     {"item_name": "Kraft paper",                      "category": "paper",        "unit_price": 0.10},
#     {"item_name": "Construction paper",               "category": "paper",        "unit_price": 0.07},
#     {"item_name": "Wrapping paper",                   "category": "paper",        "unit_price": 0.15},
#     {"item_name": "Glitter paper",                    "category": "paper",        "unit_price": 0.22},
#     {"item_name": "Decorative paper",                 "category": "paper",        "unit_price": 0.18},
#     {"item_name": "Letterhead paper",                 "category": "paper",        "unit_price": 0.12},
#     {"item_name": "Legal-size paper",                 "category": "paper",        "unit_price": 0.08},
#     {"item_name": "Crepe paper",                      "category": "paper",        "unit_price": 0.05},
#     {"item_name": "Photo paper",                      "category": "paper",        "unit_price": 0.25},
#     {"item_name": "Uncoated paper",                   "category": "paper",        "unit_price": 0.06},
#     {"item_name": "Butcher paper",                    "category": "paper",        "unit_price": 0.10},
#     {"item_name": "Heavyweight paper",                "category": "paper",        "unit_price": 0.20},
#     {"item_name": "Standard copy paper",              "category": "paper",        "unit_price": 0.04},
#     {"item_name": "Bright-colored paper",             "category": "paper",        "unit_price": 0.12},
#     {"item_name": "Patterned paper",                  "category": "paper",        "unit_price": 0.15},
# 
#     # Product Types (priced per unit)
#     {"item_name": "Paper plates",                     "category": "product",      "unit_price": 0.10},  # per plate
#     {"item_name": "Paper cups",                       "category": "product",      "unit_price": 0.08},  # per cup
#     {"item_name": "Paper napkins",                    "category": "product",      "unit_price": 0.02},  # per napkin
#     {"item_name": "Disposable cups",                  "category": "product",      "unit_price": 0.10},  # per cup
#     {"item_name": "Table covers",                     "category": "product",      "unit_price": 1.50},  # per cover
#     {"item_name": "Envelopes",                        "category": "product",      "unit_price": 0.05},  # per envelope
#     {"item_name": "Sticky notes",                     "category": "product",      "unit_price": 0.03},  # per sheet
#     {"item_name": "Notepads",                         "category": "product",      "unit_price": 2.00},  # per pad
#     {"item_name": "Invitation cards",                 "category": "product",      "unit_price": 0.50},  # per card
#     {"item_name": "Flyers",                           "category": "product",      "unit_price": 0.15},  # per flyer
#     {"item_name": "Party streamers",                  "category": "product",      "unit_price": 0.05},  # per roll
#     {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},  # per roll
#     {"item_name": "Paper party bags",                 "category": "product",      "unit_price": 0.25},  # per bag
#     {"item_name": "Name tags with lanyards",          "category": "product",      "unit_price": 0.75},  # per tag
#     {"item_name": "Presentation folders",             "category": "product",      "unit_price": 0.50},  # per folder
# 
#     # Large-format items (priced per unit)
#     {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
#     {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},
# 
#     # Specialty papers
#     {"item_name": "100 lb cover stock",               "category": "specialty",    "unit_price": 0.50},
#     {"item_name": "80 lb text paper",                 "category": "specialty",    "unit_price": 0.40},
#     {"item_name": "250 gsm cardstock",                "category": "specialty",    "unit_price": 0.30},
#     {"item_name": "220 gsm poster paper",             "category": "specialty",    "unit_price": 0.35},
# ]
# 
# # Given below are some utility functions you can use to implement your multi-agent system
# 
# def generate_sample_inventory(paper_supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
#     """
#     Generate inventory for exactly a specified percentage of items from the full paper supply list.
# 
#     This function randomly selects exactly `coverage` × N items from the `paper_supplies` list,
#     and assigns each selected item:
#     - a random stock quantity between 200 and 800,
#     - a minimum stock level between 50 and 150.
# 
#     The random seed ensures reproducibility of selection and stock levels.
# 
#     Args:
#         paper_supplies (list): A list of dictionaries, each representing a paper item with
#                                keys 'item_name', 'category', and 'unit_price'.
#         coverage (float, optional): Fraction of items to include in the inventory (default is 0.4, or 40%).
#         seed (int, optional): Random seed for reproducibility (default is 137).
# 
#     Returns:
#         pd.DataFrame: A DataFrame with the selected items and assigned inventory values, including:
#                       - item_name
#                       - category
#                       - unit_price
#                       - current_stock
#                       - min_stock_level
#     """
#     # Ensure reproducible random output
#     np.random.seed(seed)
# 
#     # Calculate number of items to include based on coverage
#     num_items = int(len(paper_supplies) * coverage)
# 
#     # Randomly select item indices without replacement
#     selected_indices = np.random.choice(
#         range(len(paper_supplies)),
#         size=num_items,
#         replace=False
#     )
# 
#     # Extract selected items from paper_supplies list
#     selected_items = [paper_supplies[i] for i in selected_indices]
# 
#     # Construct inventory records
#     inventory = []
#     for item in selected_items:
#         inventory.append({
#             "item_name": item["item_name"],
#             "category": item["category"],
#             "unit_price": item["unit_price"],
#             "current_stock": np.random.randint(200, 800),  # Realistic stock range
#             "min_stock_level": np.random.randint(50, 150)  # Reasonable threshold for reordering
#         })
# 
#     # Return inventory as a pandas DataFrame
#     return pd.DataFrame(inventory)
# 
# def init_database(db_engine: Engine, seed: int = 137) -> Engine:    
#     """
#     Set up the Munder Difflin database with all required tables and initial records.
# 
#     This function performs the following tasks:
#     - Creates the 'transactions' table for logging stock orders and sales
#     - Loads customer inquiries from 'quote_requests.csv' into a 'quote_requests' table
#     - Loads previous quotes from 'quotes.csv' into a 'quotes' table, extracting useful metadata
#     - Generates a random subset of paper inventory using `generate_sample_inventory`
#     - Inserts initial financial records including available cash and starting stock levels
# 
#     Args:
#         db_engine (Engine): A SQLAlchemy engine connected to the SQLite database.
#         seed (int, optional): A random seed used to control reproducibility of inventory stock levels.
#                               Default is 137.
# 
#     Returns:
#         Engine: The same SQLAlchemy engine, after initializing all necessary tables and records.
# 
#     Raises:
#         Exception: If an error occurs during setup, the exception is printed and raised.
#     """
#     try:
#         # ----------------------------
#         # 1. Create an empty 'transactions' table schema
#         # ----------------------------
#         transactions_schema = pd.DataFrame({
#             "id": [],
#             "item_name": [],
#             "transaction_type": [],  # 'stock_orders' or 'sales'
#             "units": [],             # Quantity involved
#             "price": [],             # Total price for the transaction
#             "transaction_date": [],  # ISO-formatted date
#         })
#         transactions_schema.to_sql("transactions", db_engine, if_exists="replace", index=False)
# 
#         # Set a consistent starting date
#         initial_date = datetime(2025, 1, 1).isoformat()
# 
#         # ----------------------------
#         # 2. Load and initialize 'quote_requests' table
#         # ----------------------------
#         quote_requests_df = pd.read_csv("quote_requests.csv")
#         quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
#         quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)
# 
#         # ----------------------------
#         # 3. Load and transform 'quotes' table
#         # ----------------------------
#         quotes_df = pd.read_csv("quotes.csv")
#         quotes_df["request_id"] = range(1, len(quotes_df) + 1)
#         quotes_df["order_date"] = initial_date
# 
#         # Unpack metadata fields (job_type, order_size, event_type) if present
#         if "request_metadata" in quotes_df.columns:
#             quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
#                 lambda x: ast.literal_eval(x) if isinstance(x, str) else x
#             )
#             quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
#             quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
#             quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))
# 
#         # Retain only relevant columns
#         quotes_df = quotes_df[[
#             "request_id",
#             "total_amount",
#             "quote_explanation",
#             "order_date",
#             "job_type",
#             "order_size",
#             "event_type"
#         ]]
#         quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)
# 
#         # ----------------------------
#         # 4. Generate inventory and seed stock
#         # ----------------------------
#         inventory_df = generate_sample_inventory(paper_supplies, coverage=1.0, seed=seed)
# 
#         # Seed initial transactions
#         initial_transactions = []
# 
#         # Add a starting cash balance via a dummy sales transaction
#         initial_transactions.append({
#             "item_name": None,
#             "transaction_type": "sales",
#             "units": None,
#             "price": 50000.0,
#             "transaction_date": initial_date,
#         })
# 
#         # Add one stock order transaction per inventory item
#         for _, item in inventory_df.iterrows():
#             initial_transactions.append({
#                 "item_name": item["item_name"],
#                 "transaction_type": "stock_orders",
#                 "units": item["current_stock"],
#                 "price": item["current_stock"] * item["unit_price"],
#                 "transaction_date": initial_date,
#             })
# 
#         # Commit transactions to database
#         pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)
# 
#         # Save the inventory reference table
#         inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)
# 
#         return db_engine
# 
#     except Exception as e:
#         print(f"Error initializing database: {e}")
#         raise
# 
# def create_transaction(
#     db_engine: Engine,
#     item_name: str,
#     transaction_type: str,
#     quantity: int,
#     price: float,
#     date: Union[str, datetime],
# ) -> int:
#     """
#     This function records a transaction of type 'stock_orders' or 'sales' with a specified
#     item name, quantity, total price, and transaction date into the 'transactions' table of the database.
# 
#     Args:
#         item_name (str): The name of the item involved in the transaction.
#         transaction_type (str): Either 'stock_orders' or 'sales'.
#         quantity (int): Number of units involved in the transaction.
#         price (float): Total price of the transaction.
#         date (str or datetime): Date of the transaction in ISO 8601 format.
# 
#     Returns:
#         int: The ID of the newly inserted transaction.
# 
#     Raises:
#         ValueError: If `transaction_type` is not 'stock_orders' or 'sales'.
#         Exception: For other database or execution errors.
#     """
#     try:
#         # Convert datetime to ISO string if necessary
#         date_str = date.isoformat() if isinstance(date, datetime) else date
# 
#         # Validate transaction type
#         if transaction_type not in {"stock_orders", "sales"}:
#             raise ValueError("Transaction type must be 'stock_orders' or 'sales'")
# 
#         # Prepare transaction record as a single-row DataFrame
#         transaction = pd.DataFrame([{
#             "item_name": item_name,
#             "transaction_type": transaction_type,
#             "units": quantity,
#             "price": price,
#             "transaction_date": date_str,
#         }])
# 
#         # Insert the record into the database
#         transaction.to_sql("transactions", db_engine, if_exists="append", index=False)
# 
#         # Fetch and return the ID of the inserted row
#         result = pd.read_sql("SELECT last_insert_rowid() as id", db_engine)
#         return int(result.iloc[0]["id"])
# 
#     except Exception as e:
#         print(f"Error creating transaction: {e}")
#         raise
# 
# def get_all_inventory(db_engine: Engine, as_of_date: str) -> Dict[str, int]:
#     """
#     Retrieve a snapshot of available inventory as of a specific date.
# 
#     This function calculates the net quantity of each item by summing 
#     all stock orders and subtracting all sales up to and including the given date.
# 
#     Only items with positive stock are included in the result.
# 
#     Args:
#         as_of_date (str): ISO-formatted date string (YYYY-MM-DD) representing the inventory cutoff.
# 
#     Returns:
#         Dict[str, int]: A dictionary mapping item names to their current stock levels.
#     """
#     # SQL query to compute stock levels per item as of the given date
#     query = """
#         SELECT
#             item_name,
#             SUM(CASE
#                 WHEN transaction_type = 'stock_orders' THEN units
#                 WHEN transaction_type = 'sales' THEN -units
#                 ELSE 0
#             END) as stock
#         FROM transactions
#         WHERE item_name IS NOT NULL
#         AND transaction_date <= :as_of_date
#         GROUP BY item_name
#         HAVING stock > 0
#     """
# 
#     # Execute the query with the date parameter
#     result = pd.read_sql(query, db_engine, params={"as_of_date": as_of_date})
# 
#     # Convert the result into a dictionary {item_name: stock}
#     return dict(zip(result["item_name"], result["stock"]))
# 
# def get_stock_level(db_engine: Engine, item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
#     """
#     Retrieve the stock level of a specific item as of a given date.
# 
#     This function calculates the net stock by summing all 'stock_orders' and 
#     subtracting all 'sales' transactions for the specified item up to the given date.
# 
#     Args:
#         item_name (str): The name of the item to look up.
#         as_of_date (str or datetime): The cutoff date (inclusive) for calculating stock.
# 
#     Returns:
#         pd.DataFrame: A single-row DataFrame with columns 'item_name' and 'current_stock'.
#     """
#     # Convert date to ISO string format if it's a datetime object
#     if isinstance(as_of_date, datetime):
#         as_of_date = as_of_date.isoformat()
# 
#     # SQL query to compute net stock level for the item
#     stock_query = """
#         SELECT
#             item_name,
#             COALESCE(SUM(CASE
#                 WHEN transaction_type = 'stock_orders' THEN units
#                 WHEN transaction_type = 'sales' THEN -units
#                 ELSE 0
#             END), 0) AS current_stock
#         FROM transactions
#         WHERE item_name = :item_name
#         AND transaction_date <= :as_of_date
#     """
# 
#     # Execute query and return result as a DataFrame
#     return pd.read_sql(
#         stock_query,
#         db_engine,
#         params={"item_name": item_name, "as_of_date": as_of_date},
#     )
# 
# def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
#     """
#     Estimate the supplier delivery date based on the requested order quantity and a starting date.
# 
#     Delivery lead time increases with order size:
#         - ≤10 units: same day
#         - 11–100 units: 1 day
#         - 101–1000 units: 4 days
#         - >1000 units: 7 days
# 
#     Args:
#         input_date_str (str): The starting date in ISO format (YYYY-MM-DD).
#         quantity (int): The number of units in the order.
# 
#     Returns:
#         str: Estimated delivery date in ISO format (YYYY-MM-DD).
#     """
#     # Debug log (comment out in production if needed)
#     print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity} from date string '{input_date_str}'")
# 
#     # Attempt to parse the input date
#     try:
#         input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
#     except (ValueError, TypeError):
#         # Fallback to current date on format error
#         print(f"WARN (get_supplier_delivery_date): Invalid date format '{input_date_str}', using today as base.")
#         input_date_dt = datetime.now()
# 
#     # Determine delivery delay based on quantity
#     if quantity <= 10:
#         days = 0
#     elif quantity <= 100:
#         days = 1
#     elif quantity <= 1000:
#         days = 4
#     else:
#         days = 7
# 
#     # Add delivery days to the starting date
#     delivery_date_dt = input_date_dt + timedelta(days=days)
# 
#     # Return formatted delivery date
#     return delivery_date_dt.strftime("%Y-%m-%d")
# 
# def get_cash_balance(db_engine: Engine, as_of_date: Union[str, datetime]) -> float:
#     """
#     Calculate the current cash balance as of a specified date.
# 
#     The balance is computed by subtracting total stock purchase costs ('stock_orders')
#     from total revenue ('sales') recorded in the transactions table up to the given date.
# 
#     Args:
#         as_of_date (str or datetime): The cutoff date (inclusive) in ISO format or as a datetime object.
# 
#     Returns:
#         float: Net cash balance as of the given date. Returns 0.0 if no transactions exist or an error occurs.
#     """
#     try:
#         if isinstance(as_of_date, datetime):
#             as_of_date = as_of_date.isoformat()
# 
#         transactions = pd.read_sql(
#             "SELECT * FROM transactions WHERE transaction_date <= :as_of_date",
#             db_engine,
#             params={"as_of_date": as_of_date},
#         )
# 
#         if not transactions.empty:
#             total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
#             total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
#             return float(total_sales - total_purchases)
# 
#         return 0.0
# 
#     except Exception as e:
#         print(f"Error getting cash balance: {e}")
#         return 0.0
# 
# 
# def generate_financial_report(db_engine: Engine, as_of_date: Union[str, datetime]) -> Dict:
#     """
#     Generate a complete financial report for the company as of a specific date.
# 
#     This includes:
#     - Cash balance
#     - Inventory valuation
#     - Combined asset total
#     - Itemized inventory breakdown
#     - Top 5 best-selling products
# 
#     Args:
#         as_of_date (str or datetime): The date (inclusive) for which to generate the report.
# 
#     Returns:
#         Dict: A dictionary containing the financial report fields:
#             - 'as_of_date': The date of the report
#             - 'cash_balance': Total cash available
#             - 'inventory_value': Total value of inventory
#             - 'total_assets': Combined cash and inventory value
#             - 'inventory_summary': List of items with stock and valuation details
#             - 'top_selling_products': List of top 5 products by revenue
#     """
#     # Normalize date input
#     if isinstance(as_of_date, datetime):
#         as_of_date = as_of_date.isoformat()
# 
#     # Get current cash balance
#     cash = get_cash_balance(db_engine, as_of_date)
# 
#     # Get current inventory snapshot
#     inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
#     inventory_value = 0.0
#     inventory_summary = []
# 
#     # Compute total inventory value and summary by item
#     for _, item in inventory_df.iterrows():
#         stock_info = get_stock_level(db_engine, item["item_name"], as_of_date)
#         stock = stock_info["current_stock"].iloc[0]
#         item_value = stock * item["unit_price"]
#         inventory_value += item_value
# 
#         inventory_summary.append({
#             "item_name": item["item_name"],
#             "stock": stock,
#             "unit_price": item["unit_price"],
#             "value": item_value,
#         })
# 
#     # Identify top-selling products by revenue
#     top_sales_query = """
#         SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
#         FROM transactions
#         WHERE transaction_type = 'sales' AND transaction_date <= :date
#         GROUP BY item_name
#         ORDER BY total_revenue DESC
#         LIMIT 5
#     """
#     top_sales = pd.read_sql(top_sales_query, db_engine, params={"date": as_of_date})
#     top_selling_products = top_sales.to_dict(orient="records")
# 
#     return {
#         "as_of_date": as_of_date,
#         "cash_balance": cash,
#         "inventory_value": inventory_value,
#         "total_assets": cash + inventory_value,
#         "inventory_summary": inventory_summary,
#         "top_selling_products": top_selling_products,
#     }
# 
# 
# def search_quote_history(db_engine: Engine, search_terms: List[str], limit: int = 5) -> List[Dict]:
#     """
#     Retrieve a list of historical quotes that match any of the provided search terms.
# 
#     The function searches both the original customer request (from `quote_requests`) and
#     the explanation for the quote (from `quotes`) for each keyword. Results are sorted by
#     most recent order date and limited by the `limit` parameter.
# 
#     Args:
#         search_terms (List[str]): List of terms to match against customer requests and explanations.
#         limit (int, optional): Maximum number of quote records to return. Default is 5.
# 
#     Returns:
#         List[Dict]: A list of matching quotes, each represented as a dictionary with fields:
#             - original_request
#             - total_amount
#             - quote_explanation
#             - job_type
#             - order_size
#             - event_type
#             - order_date
#     """
#     conditions = []
#     params = {}
# 
#     # Build SQL WHERE clause using LIKE filters for each search term
#     for i, term in enumerate(search_terms):
#         param_name = f"term_{i}"
#         conditions.append(
#             f"(LOWER(qr.response) LIKE :{param_name} OR "
#             f"LOWER(q.quote_explanation) LIKE :{param_name})"
#         )
#         params[param_name] = f"%{term.lower()}%"
# 
#     # Combine conditions; fallback to always-true if no terms provided
#     where_clause = " AND ".join(conditions) if conditions else "1=1"
# 
#     # Final SQL query to join quotes with quote_requests
#     query = f"""
#         SELECT
#             qr.response AS original_request,
#             q.total_amount,
#             q.quote_explanation,
#             q.job_type,
#             q.order_size,
#             q.event_type,
#             q.order_date
#         FROM quotes q
#         JOIN quote_requests qr ON q.request_id = qr.id
#         WHERE {where_clause}
#         ORDER BY q.order_date DESC
#         LIMIT {limit}
#     """
# 
#     # Execute parameterized query
#     with db_engine.connect() as conn:
#         result = conn.execute(text(query), params)
#         return [dict(row._mapping) for row in result]
# 
# def parse_price_from_quote(quote_response: str) -> float:
#     """
#     A robust helper to extract and sum all dollar amounts found in a string.
#     """
#     # This pattern finds all occurrences of dollar amounts
#     total_match = re.search(r'Total:\s*\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', quote_response, re.IGNORECASE)
#     
#     if total_match:
#         try:
#             price_str = total_match.group(1)
#             final_total = float(price_str.replace(',', ''))
#             print(f"--- DEBUG: Successfully parsed definitive Total as: ${final_total:.2f} ---")
#             return final_total
#         except (ValueError, IndexError):
#             print(f"--- DEBUG: Found 'Total:' but could not parse price from string '{total_match.group(1)}'. ---")
#             return 0.0
# 
#     print("--- DEBUG: No definitive 'Total: $XX.XX' pattern found in the quote response. ---")
#     return 0.0
# 
# 
# def parse_customer_request(request: str) -> List[Tuple[str, int]]:
#     """
#     Extracts item and quantity pairs from a customer request.
#     
#     Handles two formats:
#     1. Bullet lists: "- 500 sheets of A4 paper"
#     2. Sentences: "I need 500 sheets of A4 paper, 200 sheets of construction paper"
#     
#     Returns:
#         List of (item_name, quantity) tuples
#     """
#     items_found = []
#     
#     # This single, more powerful pattern handles both bulleted and sentence-based requests.
#     # It looks for a quantity, a known unit, and then captures the item name.
#     pattern = re.compile(
#         r"([\d,]+)\s+(sheets?|reams?|packets?|rolls?|flyers?|posters?|tickets?|napkins?|plates?|cups?|cards?|envelopes?|tags?|folders?|bags?|streamers?)\s*(?:of\s*)?(.+?)(?=\s*,|\s+and|\s+along with|\.|$|\n)",
#         re.IGNORECASE
#     )
# 
#     for line in request.split('\n'):
#         line = line.strip().lstrip('- ').strip()
#         if not line:
#             continue
# 
#         matches = pattern.findall(line)
#         for match in matches:
#             try:
#                 quantity_str, unit, item_name_raw = match
#                 quantity = int(quantity_str.replace(',', ''))
#                 
#                 # Re-combine the unit if it's part of the product name (e.g., "paper napkins")
#                 if unit.lower().rstrip('s') in ['flyer', 'poster', 'ticket', 'napkin', 'plate', 'cup', 'card', 'envelope', 'tag', 'folder', 'bag', 'streamer']:
#                      item_name = f"{item_name_raw.strip()} {unit.strip()}"
#                 else:
#                     item_name = item_name_raw.strip()
# 
#                 # Clean the item name
#                 item_name = re.sub(r'\s*\([^)]*\)', '', item_name).strip()
#                 item_name = " ".join(item_name.split())
# 
#                 if item_name and len(item_name) > 1:
#                     items_found.append((item_name, quantity))
#                     print(f"--- DEBUG (Final Parser): Parsed Item: '{item_name}', Quantity: {quantity} ---")
# 
#             except (ValueError, IndexError) as e:
#                 print(f"--- ERROR parsing line '{line}': {e} ---")
#                 continue
# 
#     if not items_found:
#         print("--- DEBUG: No parsable items found. ---")
#         
#     return items_found
# 
# def parse_date_from_timeline_response(response: str) -> str:
#     """
#     Parses the verbose response from the InventoryAgent to extract the date.
#     This function looks for a date in the format "Month Day, Year".
#     """
#     months = "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
#     pattern = rf"{months}\s+\d{{1,2}},\s+\d{{4}}"
#     
#     match = re.search(pattern, response)
#     
#     if match:
#         date_str = match.group(0)
#         print(f"--- DEBUG: Successfully parsed date as: {date_str} ---")
#         return date_str
#     match = re.search(r'\d{4}-\d{2}-\d{2}', response)
#     if match:
#         date_str = match.group(0)
#         print(f"--- DEBUG: Successfully parsed date as: {date_str} ---")
#         return date_str
# 
#     print("--- DEBUG: No date pattern found in the timeline response. ---")
#     return "Not Available"
# 
# def parse_transaction_id(sales_agent_response: str) -> str:
#     """
#     Extracts a transaction ID from the agent's final response string.
#     This function looks for a number following "transaction ID of" or "ID:".
#     """
#     match = re.search(r'transaction ID(?: of|:) (\d+)', sales_agent_response)
#     
#     if match:
#         transaction_id = match.group(1)
#         print(f"--- DEBUG: Successfully parsed Transaction ID as: {transaction_id} ---")
#         return transaction_id
#         
#     print("--- DEBUG: No Transaction ID pattern found in the sales agent response. ---")
#     return "N/A" 
# 
# def parse_stock_level_from_response(response: str) -> int:
#     """
#     Extracts the stock level (an integer) from the agent's response string.
#     """
#     # Look for a number associated with stock-related words
#     match = re.search(r'(?:is|have|stock:|quantity)\s*([\d,]+)', response, re.IGNORECASE)
#     if not match:
#         # Fallback: find the first sequence of digits in the response
#         match = re.search(r'(\d[\d,]*)', response)
#     
#     if match:
#         try:
#             stock_str = match.group(1).replace(',', '')
#             stock_level = int(stock_str)
#             print(f"--- DEBUG: Successfully parsed Stock Level as: {stock_level} ---")
#             return stock_level
#         except (ValueError, IndexError):
#             pass
#             
#     print(f"--- DEBUG: No stock level pattern found in response: '{response}' ---")
#     return 0
# 
# ########################
# ########################
# ########################
# # YOUR MULTI AGENT STARTS HERE
# ########################
# ########################
# ########################
# 
# # Set up and load your env parameters and instantiate your model.
# 
# 
# load_dotenv()
# nvidia_api_key = os.getenv('NVIDIA_API_KEY')
# 
# model = OpenAIServerModel(
#     model_id='gemma-7b',
#     api_base='https://integrate.api.nvidia.com/v1',
#     api_key=nvidia_api_key,
# )
# 
# # 1. Customer Relationship Agent
# class CustomerRelationshipAgent(ToolCallingAgent):
#     """An agent specializing in customer history and relationship management."""
#     def __init__(self, model):
#         super().__init__(
#             name="customer_relationship_agent",
#             description="You are a customer relationship specialist. Your goal is to find any past history related to a "
#                         "customer's inquiry to provide context for a personalized experience.",
#             tools=[get_customer_history_tool],
#             model=model
#         )
# 
# # 2. Inventory Agent
# class InventoryAgent(ToolCallingAgent):
#     """An agent specializing in warehouse stock and supplier timelines."""
#     def __init__(self, model):
#         super().__init__(
#             name="inventory_agent",
#             description=(
#             "You are an inventory management specialist. Your goal is to answer questions about product stock levels. "
#             "From the user's request, you MUST extract ONLY the simple item name (e.g., 'A4 paper', 'Cardstock', 'Glossy paper') "
#             "before calling your tools. DO NOT include quantities, descriptions, or extra words in the item_name argument."
#         ),
#             tools=[check_inventory_tool, get_delivery_timeline_tool],
#             model=model
#         )
# 
# # 3. Quotation Agent
# class QuotationAgent(ToolCallingAgent):
#     """An agent specializing in generating price quotes."""
#     def __init__(self, model):
#         super().__init__(
#             name="quotation_agent",
#             description="You are a pricing specialist. Your goal is to generate a quote for a customer. You will be given "
#                         "all necessary information. Your final output should be a clear, justified price quote. "
#                         "Remember to state if you are applying any discounts (e.g., for bulk orders) in your justification."
#                         "Use get_item_unit_price tool to find the unit price for each item.",
#             tools=[get_item_unit_price],
#             model=model
#         )
# 
# # 4. Sales Agent
# class SalesAgent(ToolCallingAgent):
#     """An agent specializing in finalizing customer sales."""
#     def __init__(self, model):
#         super().__init__(
#             name="sales_agent",
#             description="You are a sales finalization specialist. Your only job is to process a confirmed sale by creating a "
#                         "transaction record in the system.",
#             tools=[fulfill_order_tool],
#             model=model
#         )
# 
# class CustomerAgent:
#     """An agent that simulates a customer, capable of making decisions."""
#     def __init__(self, request_data: pd.Series):
#         self.request_text = request_data['request']
#         self.is_non_profit = 'non-profit' in request_data['job'].lower()
#         self.budget = 300 if self.is_non_profit else 150 
#         self.negotiation_strategy = "flexible_timeline" if self.is_non_profit else "strict_budget"
# 
#     def get_initial_request(self, date: str) -> str:
#         return f"{self.request_text} (Date of request: {date})"
# 
#     def evaluate_response(self, true_total_price: float) -> str:
#         """
#         Decides the next action based on a deterministic, true total price.
#         Defaults to "no" if the price is invalid or out of budget.
#         """
#         if 0 < true_total_price <= self.budget:
#             return "yes"
#         else:
#             return "no, that is too expensive"
# 
# 
# ########################
# ########################
# ########################
# # YOUR TOOLS STARTS HERE
# ########################
# ########################
# ########################
# 
# """Set up tools for your agents to use, these should be methods that combine the database functions above
#  and apply criteria to them to ensure that the flow of the system is correct."""
# 
# @tool
# def find_similar_inventory_item_tool(search_term: str) -> str:
#     """
#     Finds the best single item match from the inventory database based on a search term
#     by scoring items based on keyword matches.
# 
#     Args:
#         search_term (str): The item name to search for (e.g., "A4 glossy paper").
# 
#     Returns:
#         str: The single best matching item_name from the inventory, or an empty string if no good match is found.
#     """
#     print(f"--- DEBUG: Intelligent search for '{search_term}' ---")
#     
#     keywords = set(re.findall(r'\w+', search_term.lower()))
#     if not keywords:
#         return ""
# 
#     try:
#         # Fetch all item names from the inventory to score them in memory
#         all_items = pd.read_sql("SELECT item_name FROM inventory", db_engine)
#         if all_items.empty:
#             return ""
# 
#         best_match = None
#         highest_score = 0
# 
#         for item_name in all_items["item_name"]:
#             item_words = set(re.findall(r'\w+', item_name.lower()))
#             
#             # Score is the number of intersecting keywords
#             score = len(keywords.intersection(item_words))
#             
#             if score > highest_score:
#                 highest_score = score
#                 best_match = item_name
#             # If scores are equal, prefer the shorter item name (more specific)
#             elif score == highest_score and best_match and len(item_name) < len(best_match):
#                 best_match = item_name
# 
#         # Only return a match if it meets a minimum threshold of confidence (at least one keyword matched)
#         if highest_score > 0:
#             print(f"--- DEBUG: Best match found: '{best_match}' with score {highest_score} ---")
#             return best_match
#         else:
#             print("--- DEBUG: No confident match found. ---")
#             return ""
#             
#     except Exception as e:
#         print(f"--- ERROR in find_similar_inventory_item_tool: {e} ---")
#         return ""
# 
# # --- Tools for the Inventory Agent ---
# 
# @tool
# def check_inventory_tool(item_name: str, as_of_date: str) -> int:
#     """
#     Checks the current stock level for a single specified item as of a given date.
#     Returns the current stock quantity for the given item.
# 
#     Args:
#         item_name (str): The specific name of the item to check the stock for.
#         as_of_date (str): The date to check the inventory against, in ISO format.
#     """
#     stock_df = get_stock_level(db_engine, item_name=item_name, as_of_date=as_of_date)
#     if not stock_df.empty:
#         return int(stock_df.iloc[0]["current_stock"])
#     return 0
# 
# @tool
# def get_delivery_timeline_tool(quantity: int) -> str:
#     """
#     Estimates the delivery date for an out-of-stock item based on the quantity needed.
#     Returns the estimated delivery date as a string (e.g., 'YYYY-MM-DD').
# 
#     Args:
#         quantity (int): The number of units that need to be ordered from the supplier.
#     """
#     today_str = datetime.now().isoformat()
#     return get_supplier_delivery_date(input_date_str=today_str, quantity=quantity)
# 
# # --- Tool for the Customer Relationship Agent ---
# 
# @tool
# def get_customer_history_tool(search_terms: List[str]) -> List[Dict]:
#     """
#     Searches the database for past quotes matching keywords from a customer's request.
#     Returns a list of past quote dictionaries, limited to the 3 most recent.
# 
#     Args:
#         search_terms (List[str]): A list of keywords to search for in past requests and quotes.
#     """
# 
#     return search_quote_history(db_engine, search_terms=search_terms, limit=3)
# 
# # --- Tool for the Sales Agent ---
# 
# @tool
# def fulfill_order_tool(item_name: str, quantity: int, price: float, date: str) -> int:
#     """
#     Finalizes a customer sale by creating a 'sales' transaction record in the database.
#     Returns the unique ID of the newly created transaction.
# 
#     Args:
#         item_name (str): The name of the item being sold.
#         quantity (int): The number of units being sold.
#         price (float): The total final price of the transaction.
#         date (str): The date of the transaction in ISO 8601 format.
#     """
#     print(f"--- FULFILLING ORDER: Item: {item_name}, Qty: {quantity}, Price: {price}, Date: {date} ---")
#     return create_transaction(
#         db_engine,
#         item_name=item_name,
#         transaction_type="sales",
#         quantity=quantity,
#         price=price,
#         date=date
#     )
# 
# # --- Tool for the Financial Analyst Agent (or general use) ---
# 
# @tool
# def get_full_inventory_report_tool() -> Dict[str, int]:
#     """
#     Generates a full report of all items currently in stock as of today.
#     This tool does not require any arguments.
#     (This tool uses the get_all_inventory helper function).
#     """
#     today_str = datetime.now().isoformat()
#     return get_all_inventory(db_engine, as_of_date=today_str)
# 
# @tool
# def get_current_cash_balance_tool() -> float:
#     """
#     Calculates the company's current total cash balance as of today.
#     This tool does not require any arguments.
#     (This tool uses the get_cash_balance helper function).
#     """
#     today_str = datetime.now().isoformat()
#     return get_cash_balance(db_engine, as_of_date=today_str)
# 
# @tool
# def get_item_unit_price(item_name: str) -> float:
#     """
#     Retrieves the unit price for a specific item from the inventory database.
#     Args:
#         item_name (str): The name of the item to get the price for.
#     """
#     try:
#         price_df = pd.read_sql("SELECT unit_price FROM inventory WHERE item_name = :item", db_engine, params={"item": item_name})
#         if not price_df.empty:
#             return float(price_df.iloc[0]["unit_price"])
#     except Exception as e:
#         print(f"Error getting price for {item_name}: {e}")
#     return 0.0
# 
# # Set up your agents and create an orchestration agent that will manage them.
# 
# class BatchStatusLogger:
#     """A simple logger for batch processing that prints single-line updates."""
#     def __init__(self, request_id: int, job: str, event: str):
#         self.request_id = request_id
#         self.job = job
#         self.event = event
#         print(f"\n===== Request #{self.request_id}: Starting Workflow =====")
#         print(f"Context: {self.job} organizing {self.event}")
# 
#     def update(self, message: str):
#         """Prints a status update for the current request."""
#         print(f"  [Request #{self.request_id}] -> {message}")
#         
#     def finalize(self, final_response: str):
#         """Prints the final customer-facing response."""
#         print(f"  [Request #{self.request_id}] => FINAL RESPONSE: {final_response}")
#         print(f"===== Request #{self.request_id}: Workflow Complete =====")
# 
# customer_relationship_agent = CustomerRelationshipAgent(model)
# inventory_agent = InventoryAgent(model)
# quotation_agent = QuotationAgent(model)
# sales_agent = SalesAgent(model)
# 
# @tool
# def customer_relationship_tool(request: str) -> str:
#     """
#     Use this tool FIRST for any new customer request. It provides essential historical
#     context that is needed for all other steps.
#     Args:
#         request (str): The full, original text of the customer's request.
#     """
#     print("--- Orchestrator Tool: Calling Customer Relationship Agent ---")
#     return customer_relationship_agent(request)
# 
# @tool
# def inventory_tool(request: str) -> str:
#     """
#     Use this tool AFTER getting customer history to check stock levels for items
#     and to find delivery timelines if they are out of stock.
#     Args:
#         request (str): A clear, specific question about inventory (e.g., "Check stock for 500 of 'A4 Paper'").
#     """
#     print("--- Orchestrator Tool: Calling Inventory Agent ---")
#     return inventory_agent(request)
# 
# @tool
# def quotation_tool(request: str) -> str:
#     """
#     Use this tool AFTER confirming items are in stock or a delay is approved.
#     This tool generates a price quote for the customer.
#     Args:
#         request (str): A request to generate a quote, including the items, quantities, and any relevant context.
#     """
#     print("--- Orchestrator Tool: Calling Quotation Agent ---")
#     return quotation_agent(request)
# 
# @tool
# def sales_tool(request: str) -> str:
#     """
#     Use this tool LAST, only after a customer has approved a quote. 
#     This tool finalizes the sale and creates a transaction in the database.
#     Args:
#         request (str): A request to finalize a sale, including the item, quantity, and final price.
#     """
#     print("--- Orchestrator Tool: Calling Sales Agent ---")
#     return sales_agent(request)
# 
# @tool
# def parse_customer_request_tool(request: str) -> List[Tuple[str, int]]:
#     """
#     Use this tool FIRST to parse a raw customer request into a clean list of item names and quantities.
# 
#     Args:
#         request (str): The raw, original text of the customer's request.
#     """
#     return parse_customer_request(request)
# 
# class BestOrchestrator(ToolCallingAgent):
#     """
#     The master orchestrator agent that manages the entire sales and fulfillment workflow.
#     """
#     def __init__(self, model):
#         super().__init__(
#             name="orchestrator_agent",
#             description=(
#                 "You are the master orchestrator of a sales team. Your job is to process a customer request and provide a final outcome. "
#                 "You have tools to check history, check inventory, get prices, generate quotes, and finalize sales. "
#                 "Your primary goal is to determine if an order can be fulfilled. "
#                 "If an item is out of stock, your job is to report the stock level and the estimated delivery timeline for that item. "
#                 "If all items are in stock, your job is to calculate the total price, generate a quote, and finalize the sale."
#             ),
#             tools=[
#                 customer_relationship_tool,
#                 parse_customer_request_tool,
#                 inventory_tool,
#                 get_item_unit_price,
#                 quotation_tool,
#                 sales_tool
#             ],
#             model=model
#         )
#  
# # Run your test scenarios by writing them here. Make sure to keep track of them.
# 
# class TerminalAnimator:
#     """A class to create a simple, updating status animation in the terminal."""
#     def __init__(self):
#         self.ordered_keys = ['CUSTOMER REQUEST', 'HISTORY CHECK', 'INVENTORY CHECK', 'DELIVERY TIMELINE', 'QUOTE', 'SALE FINALIZED']
#         self.statuses = {key: "⏳ Pending..." for key in self.ordered_keys}
# 
#     def _clear_screen(self):
#         os.system('cls' if os.name == 'nt' else 'clear')
# 
#     def _draw(self):
#         self._clear_screen()
#         print("="*45)
#         print("===== Munder Difflin Agentic Workflow =====")
#         print("="*45)
#         for key in self.ordered_keys:
#             print(f"  - {key:<20}: {self.statuses[key]}")
#         print("-"*45)
# 
#     def update(self, key: str, message: str, delay: float = 1.0):
#         """Updates the status for a given key and redraws the display."""
#         if key in self.statuses:
#             self.statuses[key] = message
#         self._draw()
#         time.sleep(delay)
# 
#     def finalize(self, final_response: str):
#         """Prints the final customer-facing response."""
#         print("\n====== FINAL CUSTOMER-FACING RESPONSE ======")
#         print(final_response)
#         print("="*45)
# 
# def run_test_scenarios(engine: Engine):
#     
#     print("Initializing Database...")
#     init_database(engine)
#     try:
#         quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
#         quote_requests_sample["request_date"] = pd.to_datetime(
#             quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
#         )
#         quote_requests_sample.dropna(subset=["request_date"], inplace=True)
#         quote_requests_sample = quote_requests_sample.sort_values("request_date")
#     except Exception as e:
#         print(f"FATAL: Error loading test data: {e}")
#         return
# 
#     # Get initial state
#     initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
#     report = generate_financial_report(engine, initial_date)
#     current_cash = report["cash_balance"]
#     current_inventory = report["inventory_value"]
# 
#     ############
#     ############
#     ############
#     # INITIALIZE YOUR MULTI AGENT SYSTEM HERE
#     ############
#     ############
#     ############
#     
#     orchestrator = BestOrchestrator(model)
#     results = []
# 
#     for idx, row in quote_requests_sample.iterrows():
#         request_id = idx + 1
#         request_date = row["request_date"].strftime("%Y-%m-%d")
# 
#         # Process request
#         logger = BatchStatusLogger(request_id, row['job'], row['event'])
# 
#         print(f"Request Date: {request_date}")
#         print(f"Cash Balance: ${current_cash:.2f}")
#         print(f"Inventory Value: ${current_inventory:.2f}")
# 
#         customer = CustomerAgent(row)
#         initial_request = customer.get_initial_request(request_date)
#         logger.update(f"Initial Request: {initial_request}")
# 
#         # conversation_state = {
#         #     "stage": "initial_request",
#         #     "item_name": None,
#         #     "quantity": None,
#         #     "quoted_price": None,
#         #     "customer_history": None,
#         #     "is_backorder": False,
#         # }
# 
#         ############
#         ############
#         ############
#         # USE YOUR MULTI AGENT SYSTEM TO HANDLE THE REQUEST
#         ############
#         ############
#         ############
# 
#         parsed_items = parse_customer_request(initial_request)
#         
#         is_out_of_stock = False
#         final_response = ""
#         corrected_items_to_check = [] 
# 
#         if not parsed_items:
#             final_response = "Apologies, I could not understand the items in your request."
#             logger.finalize(final_response)
#         else:
#             for item_name, quantity in parsed_items:
#                 stock_level = check_inventory_tool(item_name, as_of_date=request_date)
#                 
#                 if stock_level <= 0:
#                     logger.update(f"Exact match for '{item_name}' not in stock. Searching for a similar item.")
#                     corrected_item_name = find_similar_inventory_item_tool(item_name)
#                     
#                     if corrected_item_name:
#                         stock_level = check_inventory_tool(corrected_item_name, as_of_date=request_date)
#                         item_name = corrected_item_name
#                     else:
#                         is_out_of_stock = True
#                         final_response = f"Apologies, but '{item_name}' is not an item we carry. We cannot proceed."
#                         break
#                 
#                 logger.update(f"Checking inventory for '{item_name}': {stock_level} available, {quantity} requested.")
#                 if stock_level < quantity:
#                     is_out_of_stock = True
#                     final_response = f"Apologies, but we only have {stock_level} of '{item_name}' in stock."
#                     break
#                 
#                 corrected_items_to_check.append((item_name, quantity))
# 
#             if not is_out_of_stock:
#                 logger.update("All items in stock. Generating quote.")
#                 
#                 true_total_price = 0
#                 for item_name, quantity in corrected_items_to_check:
#                     unit_price = get_item_unit_price(item_name)
#                     true_total_price += unit_price * quantity
#                 
#                 orchestrator_response = f"Here is the final quote for your order:\nTotal: ${true_total_price:.2f}"
#                 logger.update(f"Generated Quote: {orchestrator_response}")
# 
#                 customer_decision = customer.evaluate_response(true_total_price)
#                 logger.update(f"Customer decision: '{customer_decision}'")
# 
#                 if customer_decision == "yes":
#                     if true_total_price > 0:
#                         for item_name, quantity in corrected_items_to_check:
#                             item_price = get_item_unit_price(item_name)
#                             transaction_price = item_price * quantity
#                             fulfill_order_tool(item_name, quantity, transaction_price, date=request_date)
#                         
#                         final_response = f"Sale finalized for {len(corrected_items_to_check)} item(s) with a total value of ${true_total_price:.2f}."
#                     else:
#                         final_response = "Customer approved, but a total price of zero was calculated. Sale not finalized."
#                 else:
#                     final_response = "The customer did not approve the quote. The order has been cancelled."
#             
#             logger.finalize(final_response)
# 
#         report = generate_financial_report(engine, request_date)
#         current_cash = report["cash_balance"]
#         current_inventory = report["inventory_value"]
# 
#         print(f"Response: {final_response}")
#         print(f"Updated Cash: ${current_cash:.2f}")
#         print(f"Updated Inventory: ${current_inventory:.2f}")
#         # --- END: CLEAN PRINTING LOGIC ---
#         
#         results.append({
#             "request_id": request_id,
#             "request_date": request_date,
#             "cash_balance": current_cash,
#             "inventory_value": current_inventory,
#             "response": final_response,
#         })
#         time.sleep(1)
# 
#     # Final report
#     final_report_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
#     final_report = generate_financial_report(engine, final_report_date)
#     print("\n===== FINAL FINANCIAL REPORT =====")
#     print(f"Final Cash: ${final_report['cash_balance']:.2f}")
#     print(f"Final Inventory: ${final_report['inventory_value']:.2f}")
# 
#     pd.DataFrame(results).to_csv("test_results.csv", index=False)
#     return results
# 
# def run_single_simulation(engine: Engine, request_row: pd.Series):
#     """
#     Runs a guided, robust, agentic simulation for a SINGLE customer request.
#     """
#     print("\n\n===== Starting SINGLE Agentic Simulation =====")
# 
#     logger = BatchStatusLogger(
#         request_id=request_row.name + 1, 
#         job=request_row['job'], 
#         event=request_row['event']
#     )
#     
#     orchestrator = BestOrchestrator(model) 
#     customer = CustomerAgent(request_row)
#     request_date = datetime.now().strftime("%Y-%m-%d")
# 
#     current_request = customer.get_initial_request(request_date)
#     logger.update(f"Initial Request: {current_request}")
#     print(f"--- Customer Request ---\n{current_request}\n---")
#     
#     print("\n--- Phase 1: Context Gathering ---")
#     history_response = orchestrator(f"First, get the customer history for this request: {current_request}")
#     logger.update(f"Initial Request: {current_request}")
#     print(f"Orchestrator History Analysis: {history_response}")
# 
#     print("\n--- Phase 2: Inventory Check ---")
#     parsed_items = parse_customer_request(current_request)
#     is_out_of_stock = False
#     
#     for item_name, quantity in parsed_items:
#         print(f"Checking stock for: {item_name}...")
#         stock_response = orchestrator(f"Use your inventory_tool to check the stock for exactly this item: '{item_name}'")
#         stock_level = parse_stock_level_from_response(stock_response)
#         
#         if stock_level < quantity:
#             is_out_of_stock = True
#             logger.update(f"Item is OUT OF STOCK. Getting timeline...")
#             print(f"  -> RESULT: OUT OF STOCK ({stock_level} available)")
#             
#             print("\n--- Phase 3a: Getting Delivery Timeline ---")
#             timeline_response = orchestrator(f"The item '{item_name}' is out of stock. Use your inventory_tool to get the delivery timeline for a new order.")
#             timeline_date = parse_date_from_timeline_response(timeline_response)
#             
#             print(f"\nFINAL AGENT RESPONSE: Apologies, '{item_name}' is out of stock. The estimated delivery for a new order is {timeline_date}.")
#             logger.finalize("Workflow ended due to out of stock item.")
#             return
#         else:
#             print(f"  -> RESULT: IN STOCK ({stock_level} available)")
# 
#     if not is_out_of_stock:
#         print("\n--- Phase 3b: Generating Quote ---")
#         quote_request_text = " and ".join([f"{qty} of '{name}'" for name, qty in parsed_items])
#         final_quote_response = orchestrator(f"All items are in stock. Now, generate a full price quote for the following order: {quote_request_text}")
#         
#         print(f"\nFINAL AGENT RESPONSE: {final_quote_response}")
# 
# 
# 
# if __name__ == "__main__":
#     db_path = "munder_difflin.db"
# 
#     if os.path.exists(db_path):
#         print("--- Existing database found. Removing it to start fresh. ---")
#         os.remove(db_path)
#     
#     print("--- Initializing a new one. ---")
#     init_database(db_engine)
#     print("--- Database initialized successfully. ---")
# 
#     print("\n--- Starting BATCH processing of ALL requests ---")
#     batch_results = run_test_scenarios(db_engine)
#     print("\n--- Batch processing complete. Results saved to test_results_final.csv ---")
# 
