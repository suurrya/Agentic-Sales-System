# Munder Difflin Agent Automation

This project implements a simulated multi-agent system for a fictional paper company, "Munder Difflin". Powered by `smolagents`, the system uses various AI agents seamlessly orchestrated to analyze customer orders, track inventory, execute history checks, give automated pricing, and finalize sales into a SQLite database. 

## Key Features
- **Customer Relationship Agent**: Queries historic sales databases to enrich interactions.
- **Inventory Agent**: Checks available paper supplies levels via database queries.
- **Quotation Agent**: Constructs unit prices into aggregated and sensible quote bills.
- **Sales Agent**: Finalizes deals and commits the records.
- **Master Orchestrator**: Uses dynamic planning to pass contexts between agents to resolve the customer's request. 

## Modular Architecture
The initial monolithic codebase has been refactored into a scalable, modular structure:
- `database.py`: All relational database schema setup, raw SQL commands, and base data structures.
- `tools.py`: Python callable tools wrapped for `smolagents` function calling.
- `agents.py`: System configurations encapsulating character traits, individual tools, and behaviors.
- `main.py`: The executing entry point for bootstrapping and scaling out automated request evaluations.

## Requirements
- Python 3.10+
- See `requirements.txt` for typical python library requirements.

## How to run the project
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure settings by adding your chosen API key:
   Set `NVIDIA_API_KEY` in the `.env` file. The local setup employs `gemma-7b`.
3. Launch the workflow:
   ```bash
   python main.py
   ```
4. **Capacity Testing**: Upon running `main.py`, the system will automatically dynamically generate a 50-row scaled load-test queue reflecting differing job scopes.
5. **Simulated Processing**: The master orchestrator will loop through every request to process simulated sales workflows. Output data gets recorded to two structures simulating typical database pipelines:
   - `olap_database.csv`: A generated table representing a flattened data warehouse structure (Cash levels, total inventory valuation, etc.) for high-level business analytics.
   - `oltp_database.csv`: Intricate transactional logs describing items fulfilled, transaction timestamps, routing boolean metrics, and request IDs designed for high volume operational pipelines.
