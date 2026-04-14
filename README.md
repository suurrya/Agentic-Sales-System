# Munder Difflin — Agentic Sales System

A multi-agent AI system that simulates an end-to-end sales pipeline for a fictional paper supply company. Built with [smolagents](https://github.com/huggingface/smolagents), it orchestrates a team of specialised agents to handle customer quote requests — from history lookup and inventory checks through to pricing, negotiation, and transaction recording.

---

## What It Does

The system processes incoming customer quote requests in a fully automated loop:

1. **Parse** the raw request into item names and quantities
2. **Look up** relevant quote history for context
3. **Check** warehouse stock levels and estimate delivery timelines
4. **Generate** an itemised price quote
5. **Simulate** the customer accepting or rejecting the quote based on their budget
6. **Finalise** accepted sales by writing a transaction record to the database
7. **Export** results to OLAP and OLTP CSV files for downstream analytics

---

## Architecture

The system is built on a **hierarchical multi-agent** design using `smolagents`:

```
BestOrchestrator  (master planner)
├── CustomerRelationshipAgent   — searches past quote history
├── InventoryAgent              — checks stock levels + delivery timelines
├── QuotationAgent              — calculates item prices and discounts
└── SalesAgent                  — records confirmed transactions to SQLite
```

Each specialised agent exposes a natural-language interface to the orchestrator via `@tool`-wrapped callables. The orchestrator dynamically decides which agents to invoke and in what order, passing context between them to resolve the full request.

A separate `CustomerAgent` class simulates the customer side of the negotiation — it holds a budget (£150 standard / £300 non-profit) and returns `"yes"` or `"no, that is too expensive"` based on the quoted total.

---

## Agent Roles & Tools

| Agent | Role | Tools Available |
|---|---|---|
| `BestOrchestrator` | Plans and coordinates the full workflow | All sub-agent tools + `parse_customer_request`, `get_item_unit_price`, `get_delivery_timeline` |
| `CustomerRelationshipAgent` | Retrieves relevant past quotes for context | `get_customer_history_tool` |
| `InventoryAgent` | Checks live stock levels and delivery dates | `check_inventory_tool`, `get_delivery_timeline_tool`, `find_similar_inventory_item_tool` |
| `QuotationAgent` | Builds itemised quotes with optional discounts | `get_item_unit_price`, `find_similar_inventory_item_tool` |
| `SalesAgent` | Commits confirmed sales to the database | `fulfill_order_tool` |

---

## File Structure

```
Agentic Sales System/
│
├── main.py                          # Entry point — batch processing loop
├── requirements.txt                 # Python dependencies
├── .env                             # API keys (not committed)
│
├── src/
│   ├── agents/
│   │   ├── orchestrator.py          # BestOrchestrator + tool wrappers for sub-agents
│   │   ├── specialized.py           # CustomerRelationship, Inventory, Quotation, Sales agents
│   │   └── customer.py              # CustomerAgent — simulates customer decision-making
│   │
│   ├── tools/
│   │   ├── history_tools.py         # get_customer_history_tool
│   │   ├── inventory_tools.py       # check_inventory_tool, find_similar_inventory_item_tool
│   │   ├── pricing_tools.py         # get_item_unit_price, get_full_inventory_report_tool, get_current_cash_balance_tool
│   │   └── fulfillment_tools.py     # fulfill_order_tool, get_delivery_timeline_tool
│   │
│   ├── database/
│   │   └── database.py              # DB init, transactions, stock queries, financial reports, quote history search
│   │
│   └── utils/
│       ├── parsers.py               # Free-text parsers for requests, prices, stock levels, dates, transaction IDs
│       └── logger.py                # BatchStatusLogger, TerminalAnimator
│
├── data/
│   ├── input/
│   │   ├── quote_requests.csv       # Raw customer quote requests (batch input)
│   │   └── quotes.csv               # Historical quote records for seeding the DB
│   └── output/
│       ├── olap_database.csv        # Flattened analytics snapshot (cash, inventory value, etc.)
│       └── oltp_database.csv        # Transactional log (item, price, timestamp, request ID)
│
├── db/
│   └── munder_difflin.db            # SQLite database (auto-created on first run)
│
└── reference/
    └── project_starter.py           # Original monolithic reference implementation
```

---

## Database Schema

Backed by **SQLite** via **SQLAlchemy**, with four tables:

| Table | Description |
|---|---|
| `inventory` | Master catalogue of paper products with unit prices and minimum stock levels |
| `transactions` | All stock orders and sales events (item, units, price, date) |
| `quote_requests` | Raw inbound customer requests |
| `quotes` | Generated quotes linked to requests (total amount, explanation, job/event metadata) |

Stock levels are computed at query time by summing `stock_orders` minus `sales` transactions up to a given date — no separate stock counter column is maintained.

---

## Output Files

After a batch run, two CSV files are written to `data/output/`:

- **`oltp_database.csv`** — Row-level transactional log. Contains one row per fulfilled order with item name, quantity, sale price, delivery date, transaction ID, and the originating request ID. Designed for operational pipelines.

- **`olap_database.csv`** — Aggregated business snapshot per processed request. Contains cash balance, total inventory valuation, and top-selling products. Designed for analytics and dashboards.

---

## Setup & Running

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd "Agentic Sales System"
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your API key

Create a `.env` file in the project root:

```env
NVIDIA_API_KEY=your_key_here
```

The default model is `gemma-7b` served via the NVIDIA API.

### 3. Run the batch pipeline

```bash
python main.py
```

On first run, `main.py` initialises the SQLite database, seeds inventory and historical quotes, then processes the full batch of quote requests from `data/input/quote_requests.csv`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | [smolagents](https://github.com/huggingface/smolagents) (HuggingFace) |
| LLM backend | NVIDIA NIM API — `gemma-7b` |
| Database | SQLite via SQLAlchemy |
| Data processing | pandas, numpy |
| Config | python-dotenv |
| Python | 3.10+ |
