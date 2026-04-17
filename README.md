# PaperTrail Co. — Agentic Sales System

> *Every sheet. Every deal. Tracked.*

A multi-agent AI system that automates an end-to-end sales pipeline for a paper supply company. Built with [smolagents](https://github.com/huggingface/smolagents) and LLaMA-3.3-70b-instruct (via NVIDIA NIM), it orchestrates a team of specialised agents to handle customer quote requests — from inventory checks and pricing through to negotiation, transaction recording, and a live web UI.

---

## What It Does

The system processes incoming customer quote requests in a fully automated pipeline:

1. **Parse** the raw request into item names and quantities
2. **Check** warehouse stock directly via SQL — no LLM round-trip, ~100× faster
3. **Generate** an itemised price quote with optional discounts
4. **Negotiate** — the customer agent evaluates the quote against their budget and can counter-offer via LLM
5. **Finalise** accepted sales by writing a transaction record to the database
6. **Verify** fulfilment by counting new DB rows — detects hallucinations where the agent claims success without writing any data
7. **Export** results to OLAP and OLTP CSV files for downstream analytics
8. **Serve** a live web UI: customer order portal, live OLTP feed, and analytics dashboard

---

## Architecture

The system follows a **hierarchical multi-agent** design with a `BestOrchestrator` coordinator at the top level. The orchestrator holds all sub-agents as registered tools and uses LLM-driven planning to decide which agents to invoke and in what order, passing context between them to resolve the full request.

```
BestOrchestrator  (master coordinator — LLM-driven planning)
├── gather_context_tool         → CustomerRelationshipAgent + InventoryAgent (parallel)
├── quotation_tool              → QuotationAgent
├── sales_tool                  → SalesAgent
├── parse_customer_request_tool → regex/JSON parser (no LLM)
├── get_item_unit_price         → direct DB lookup
├── get_delivery_timeline_tool  → direct DB lookup
└── find_similar_inventory_item_tool → fuzzy catalogue match

CustomerAgent                   — simulates the buyer side of negotiation (LLM-powered)
```

`BestOrchestrator` is implemented in `src/agents/orchestrator.py` alongside `create_orchestrator_tools()`, which wraps every sub-agent as a smolagents `@tool` and registers the full tool list with the coordinator.

### Performance-optimised execution path

For high-throughput batch processing (`evaluator/evaluation.py`) and the web UI (`ui/app.py`), the pipeline calls specialised agents directly rather than routing each request through the orchestrator's LLM planning loop. This eliminates one extra LLM call per phase — a significant saving on a rate-limited free-tier API where each call costs 150–200 s.

```
evaluator/evaluation.py / ui/app.py  (direct-dispatch path)
│
├── Phase 1 — Inventory check (direct SQL, asyncio.gather — no LLM)
│   └── find_similar_inventory_item_tool → check_inventory_tool
│
├── Phase 2 — Quote generation
│   └── QuotationAgent  ──  get_item_unit_price, find_similar_inventory_item_tool
│
├── Phase 3 — Customer negotiation
│   └── CustomerAgent  ──  LLM reasoning only (no tools)
│
└── Phase 4 — Fulfilment
    └── SalesAgent  ──  fulfill_order_tool → SQLite INSERT
```

The orchestrator architecture and all its tooling remain fully intact — switching back to coordinator-driven execution requires only instantiating `BestOrchestrator` in the entry point.

### Parallel inventory checks

All items in a request are checked concurrently via `asyncio.gather()` + `ThreadPoolExecutor`. The canonical catalogue name is resolved first (`find_similar_inventory_item_tool`) so case/spelling differences between the customer request and the DB record never produce false zero-stock results.

### Concurrency guard

`ResilientOpenAIModel` holds a `threading.Semaphore(2)` shared across every agent instance. NVIDIA's free tier throttles at 3+ concurrent API calls; the semaphore caps active calls at 2 while still allowing some parallelism. If a call returns empty or times out (30 s hard limit), the model retries up to 3 times with exponential backoff and jitter (±1–2 s) to prevent thundering-herd collisions.

### JSON repair + type coercion

LLaMA-3.3-70b occasionally produces single-quoted JSON or passes numeric values as strings (`"quantity": "300"`). Two monkey-patches on smolagents handle this transparently:

- **`_resilient_parse_json_blob`** — repairs malformed JSON with `json-repair`, then coerces `{"parameters": {"quantity": "300"}}` → `int/float` (Path A: text agents)
- **`_resilient_parse_json_if_needed`** — coerces the flat argument dict returned by `ToolCallingAgent` structured tool calls (Path B). Both `smolagents.models` and `smolagents.agents` namespaces are patched because `agents.py` imports the function at the top level, creating its own reference.

### Hallucination detection

Before the sales agent runs, the current maximum transaction `id` is snapshotted. After the agent reports success, the pipeline counts new `sales` rows with `id > snapshot`. If the count is zero the agent hallucinated — the order is not recorded as fulfilled.

### Structured output parsing

Agent responses are parsed with a two-layer strategy: JSON-first (validated against Pydantic schemas) with regex as a fallback. Agents that return well-formed JSON get zero-cost schema validation; agents that return natural language still work without changes.

### Retry + fallback

Every agent call is wrapped with `_with_retry` (exponential backoff). On total failure a graceful fallback string is returned so the pipeline continues rather than crashing.

---

## Agent Roles & Tools

| Agent | Role | Tools |
|---|---|---|
| `QuotationAgent` | Builds itemised quotes with optional discounts | `get_item_unit_price`, `find_similar_inventory_item_tool` |
| `SalesAgent` | Commits confirmed sales to the database | `fulfill_order_tool` |
| `CustomerAgent` | Simulates the buyer — accepts, counter-offers, or declines | *(LLM reasoning only)* |
| `InventoryAgent` | Checks live stock levels (used for standalone queries) | `check_inventory_tool`, `get_delivery_timeline_tool`, `find_similar_inventory_item_tool` |
| `CustomerRelationshipAgent` | Retrieves relevant past quotes for context | `get_customer_history_tool` |

---

## Web UI

The web application (`ui/app.py`) is a three-page NiceGUI app running on **port 8080**:

### `/` — Customer Order Portal

A form where customers describe what they need. On submit, the full pipeline runs in the browser tab with live status updates at each stage:

```
Parsing your request...
→ Checking stock for 3 item(s)...
→ Generating price quote...
→ Quote: $240.00 — evaluating against budget...
→ Accepted at $240.00! Processing fulfilment...
→ Sale finalized at $240.00!
```

The result card turns green on success or amber on rejection/out-of-stock.

### `/live` — OLTP Live Feed

Reads the `transactions` table directly from SQLite and auto-refreshes every 5 seconds. Shows:
- 5 KPI cards: total transactions, sales orders, stock orders, total revenue, average sale value
- Paginated transaction table (last 200 rows, most recent first)

### `/analytics` — OLAP Analytics Dashboard

Combines batch CSV output and live DB aggregates:
- Live cash balance and sales count (from DB)
- Batch fulfillment rate, request count, and revenue (from CSV)
- Cash balance over time (line chart)
- Inventory value over time (line chart)
- Fulfillment rate by customer type (bar chart)
- Revenue by event type (bar chart)
- Top 10 selling products by revenue (live from DB)

---

## File Structure

```
Agentic Sales System/
│
├── evaluator/
│   ├── evaluation.py                # Batch test runner — 50 requests, async pipeline
│   └── evaluator.py                 # Pipeline evaluator — hard-coded metrics + LLM analysis
├── requirements.txt                 # Annotated Python dependencies
├── .env                             # API keys (not committed)
│
├── ui/
│   ├── app.py                       # PaperTrail Co. web UI — 3 pages on port 8080
│   └── dashboard.py                 # Legacy static analytics dashboard (port 8001)
│
├── src/
│   ├── agents/
│   │   ├── orchestrator.py          # _with_retry, _gather_context helpers
│   │   ├── specialized.py           # QuotationAgent, SalesAgent, InventoryAgent, CustomerRelationshipAgent
│   │   ├── customer.py              # CustomerAgent — LLM negotiation loop
│   │   └── prompts.py               # System prompt strings for all agents
│   │
│   ├── tools/
│   │   ├── history_tools.py         # get_customer_history_tool
│   │   ├── inventory_tools.py       # check_inventory_tool, find_similar_inventory_item_tool
│   │   ├── pricing_tools.py         # get_item_unit_price, get_full_inventory_report_tool
│   │   └── fulfillment_tools.py     # fulfill_order_tool, get_delivery_timeline_tool
│   │
│   ├── database/
│   │   ├── database.py              # DB init, DDL schema, transactions, stock queries, financial reports
│   │   └── reset.py                 # Database reset — wipes sales history, restores stock, appends CSV events
│   │
│   └── utils/
│       ├── model_wrapper.py         # ResilientOpenAIModel + JSON-repair monkey-patches
│       ├── parsers.py               # Pydantic schemas + JSON-first / regex-fallback parse functions
│       └── logger.py                # BatchStatusLogger, PipelineLogger, AgentFailureLogger
│
├── data/
│   ├── input/
│   │   ├── quote_requests.csv       # Historical quote requests (used to seed DB)
│   │   ├── quote_requests_sample.csv # Generated batch input (50 requests, auto-created)
│   │   └── quotes.csv               # Historical quote records for seeding the DB
│   └── output/
│       ├── olap_database.csv        # Aggregated analytics snapshot per request
│       ├── oltp_database.csv        # Row-level transactional log
│       ├── pipeline_log.txt         # Per-step latency log for each request
│       └── agent_failures.jsonl     # Structured failure log (created at runtime)
│
└── db/
    └── munder_difflin.db            # SQLite database (auto-created on first run)
```

---

## Database Schema

Backed by **SQLite** via **SQLAlchemy**, with four tables:

| Table | Description |
|---|---|
| `transactions` | All stock orders and sales events — `id` is `INTEGER PRIMARY KEY AUTOINCREMENT` so `last_insert_rowid()` and hallucination detection work correctly |
| `inventory` | Master catalogue of paper products with unit prices and stock levels |
| `quote_requests` | Raw inbound customer requests |
| `quotes` | Generated quotes linked to requests (total amount, explanation, job/event metadata) |

Stock levels are computed at query time by summing `stock_orders` minus `sales` transactions up to a given date — no separate stock counter column is maintained.

---

## Output Files

After a batch run, four files are written to `data/output/`:

- **`oltp_database.csv`** — Row-level transactional log. One row per processed request: fulfilled flag, items checked/fulfilled, total value, timestamp.

- **`olap_database.csv`** — Aggregated business snapshot per request. Contains cash balance, total inventory valuation, and the final response. Designed for the analytics dashboard.

- **`pipeline_log.txt`** — Plain-text latency report. One block per request showing per-step durations, total time, outcome, and reason.

- **`agent_failures.jsonl`** — Structured JSONL failure log. One JSON object per line: timestamp, agent name, request ID, attempt number, error type, error message.

---

## Setup & Running

### 1. Clone and install

```bash
git clone <repo-url>
cd "Agentic Sales System"
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your API key

```env
# .env
NVIDIA_API_KEY=your_key_here
```

The model is `meta/llama-3.3-70b-instruct` served via the NVIDIA NIM API.

### 3. Run the web UI

```bash
python ui/app.py
```

Open **http://localhost:8080** to place orders, watch the live transaction feed, and view analytics. The database is initialised automatically on first launch if it does not exist.

### 4. Run batch evaluation

```bash
python evaluator/evaluation.py              # Process all 50 generated requests
python evaluator/evaluation.py --limit 5    # Process only the first 5 (faster for testing)
```

`evaluation.py` generates 50 test requests in `data/input/quote_requests_sample.csv`, resets the database, and processes all requests concurrently (up to 5 at a time). Results are written to `data/output/test_results_log.txt`.

```bash
python evaluator/evaluator.py           # Full evaluation report + LLM qualitative analysis
python evaluator/evaluator.py --no-llm  # Hard-coded metrics only (instant, no API call)
```

`evaluator.py` parses the log produced by `evaluation.py` and outputs a structured report covering fulfillment rates, per-step latency (avg/min/max/p95), revenue, and hallucination counts. The optional LLM layer provides qualitative analysis and a pipeline score.

### 5. Reset the database

```bash
python src/database/reset.py
```

Wipes all sales history, restores inventory to initial levels, and appends a stock-replenishment event to the OLTP and OLAP CSV files.

### 6. Legacy static dashboard (optional)

```bash
python ui/dashboard.py
```

Open **http://localhost:8001** for the original static analytics dashboard. Reads from the CSV output files — run `evaluator/evaluation.py` first.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | [smolagents](https://github.com/huggingface/smolagents) (HuggingFace) |
| LLM backend | NVIDIA NIM API — `meta/llama-3.3-70b-instruct` |
| Concurrency | `asyncio.gather` + `ThreadPoolExecutor` + `threading.Semaphore` |
| JSON robustness | [json-repair](https://github.com/mangiucugna/json_repair) + custom monkey-patches on smolagents |
| Structured output | [Pydantic v2](https://docs.pydantic.dev/) — JSON-first parsing at agent boundaries |
| Database | SQLite via SQLAlchemy (DDL schema with `AUTOINCREMENT`) |
| Web UI | [NiceGUI](https://nicegui.io/) v3.10 with Apache ECharts |
| Data processing | pandas, numpy |
| Config | python-dotenv |
| Python | 3.10+ |
