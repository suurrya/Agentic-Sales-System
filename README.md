# Munder Difflin — Agentic Sales System

A multi-agent AI system that simulates an end-to-end sales pipeline for a fictional paper supply company. Built with [smolagents](https://github.com/huggingface/smolagents), it orchestrates a team of specialised agents to handle customer quote requests — from history lookup and inventory checks through to pricing, negotiation, and transaction recording.

---

## What It Does

The system processes incoming customer quote requests in a fully automated loop:

1. **Parse** the raw request into item names and quantities
2. **Look up** relevant quote history and **check** warehouse stock — both at the same time (parallel)
3. **Generate** an itemised price quote with optional discounts
4. **Negotiate** — the customer agent evaluates the quote against their budget and can counter-offer via LLM
5. **Finalise** accepted sales by writing a transaction record to the database
6. **Export** results to OLAP and OLTP CSV files for downstream analytics
7. **Visualise** the batch run in a live NiceGUI dashboard

---

## Architecture

The system is built on a **hierarchical multi-agent** design using `smolagents`:

```
BestOrchestrator  (master planner)
├── CustomerRelationshipAgent   — searches past quote history
├── InventoryAgent              — checks stock levels + delivery timelines  ─┐ concurrent
│                                                                             └─ via asyncio.gather
├── QuotationAgent              — calculates item prices and discounts
└── SalesAgent                  — records confirmed transactions to SQLite

CustomerAgent                   — simulates the buyer side of negotiation (LLM-powered)
```

Each specialised agent exposes a natural-language interface to the orchestrator via `@tool`-wrapped callables. The orchestrator dynamically decides which agents to invoke and in what order, passing context between them to resolve the full request.

### Parallel context gathering

`CustomerRelationshipAgent` and `InventoryAgent` have no dependency on each other, so they are dispatched concurrently via `asyncio.gather()` + `ThreadPoolExecutor`. On large batches this halves the latency of the context-gathering phase compared to sequential calls.

### Retry + fallback

Every agent tool call is wrapped with `_with_retry` (exponential backoff: 1 s → 2 s → 4 s). On total failure a graceful fallback string is returned so the pipeline continues rather than crashing. Every failure is appended to `data/output/agent_failures.jsonl` by `AgentFailureLogger` for post-run diagnostics.

### Structured output parsing

Agent responses are parsed with a two-layer strategy: JSON-first (validated against Pydantic schemas) with regex as a fallback. This means agents that return well-formed JSON get zero-cost schema validation; agents that return natural language still work without changes.

---

## Agent Roles & Tools

| Agent | Role | Tools Available |
|---|---|---|
| `BestOrchestrator` | Plans and coordinates the full workflow | All sub-agent tools + `parse_customer_request`, `get_item_unit_price`, `get_delivery_timeline` |
| `CustomerRelationshipAgent` | Retrieves relevant past quotes for context | `get_customer_history_tool` |
| `InventoryAgent` | Checks live stock levels and delivery dates | `check_inventory_tool`, `get_delivery_timeline_tool`, `find_similar_inventory_item_tool` |
| `QuotationAgent` | Builds itemised quotes with optional discounts | `get_item_unit_price`, `find_similar_inventory_item_tool` |
| `SalesAgent` | Commits confirmed sales to the database | `fulfill_order_tool` |
| `CustomerAgent` | Simulates the buyer — accepts, counter-offers, or declines | *(no tools — LLM reasoning only)* |

---

## File Structure

```
Agentic Sales System/
│
├── main.py                          # Entry point — batch processing loop
├── dashboard.py                     # NiceGUI analytics dashboard (run separately)
├── requirements.txt                 # Annotated Python dependencies
├── .env                             # API keys (not committed)
│
├── src/
│   ├── agents/
│   │   ├── orchestrator.py          # BestOrchestrator, _with_retry, _gather_context, tool wrappers
│   │   ├── specialized.py           # CustomerRelationship, Inventory, Quotation, Sales agents
│   │   └── customer.py              # CustomerAgent — LLM negotiation loop
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
│       ├── parsers.py               # Pydantic schemas + JSON-first / regex-fallback parse functions
│       └── logger.py                # BatchStatusLogger, TerminalAnimator, AgentFailureLogger
│
├── data/
│   ├── input/
│   │   ├── quote_requests.csv       # Raw customer quote requests (batch input)
│   │   └── quotes.csv               # Historical quote records for seeding the DB
│   └── output/
│       ├── olap_database.csv        # Aggregated analytics snapshot per request
│       ├── oltp_database.csv        # Row-level transactional log
│       └── agent_failures.jsonl     # Structured failure log (created at runtime)
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

After a batch run, three files are written to `data/output/`:

- **`oltp_database.csv`** — Row-level transactional log. One row per processed request with item name, quantity, sale price, delivery date, transaction ID, and the originating request ID.

- **`olap_database.csv`** — Aggregated business snapshot per request. Contains cash balance, total inventory valuation, and the orchestrator's final response. Designed for analytics and the dashboard.

- **`agent_failures.jsonl`** — Structured JSONL failure log written by `AgentFailureLogger`. One JSON object per line: timestamp, agent name, request ID, attempt number, error type, error message. Consumed by the dashboard failure panel.

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

### 4. Launch the dashboard

```bash
python dashboard.py
```

Open `http://localhost:8080` to view the live analytics dashboard. The dashboard reads from the CSV output files, so run `main.py` at least once first.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | [smolagents](https://github.com/huggingface/smolagents) (HuggingFace) |
| LLM backend | NVIDIA NIM API — `gemma-7b` |
| Concurrency | `asyncio.gather` + `ThreadPoolExecutor` |
| Structured output | [Pydantic v2](https://docs.pydantic.dev/) — JSON-first parsing at agent boundaries |
| Database | SQLite via SQLAlchemy |
| Dashboard | [NiceGUI](https://nicegui.io/) with Apache ECharts |
| Data processing | pandas, numpy |
| Config | python-dotenv |
| Python | 3.10+ |
