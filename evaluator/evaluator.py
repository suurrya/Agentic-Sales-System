"""
evaluator.py
============
Evaluates the PaperTrail Co. agentic sales pipeline after a batch test run.

Two-layer evaluation
--------------------
  1. Hard-coded metrics  — parse test_results_log.txt and compute:
       • Fulfillment rate and failure breakdown
       • Per-step latency (avg / min / max / p95)
       • Revenue summary (total, average order value)
       • Hallucination and parser-fallback detection

  2. LLM evaluation agent — receives the computed metrics and writes a
       qualitative analysis: strengths, weaknesses, and recommendations.

Run from the project root after evaluation.py completes:

    python evaluator/evaluator.py
    python evaluator/evaluator.py --no-llm    # skip LLM step
"""

import os
import sys
import re
import json
import argparse
import statistics
from datetime import datetime

# Allow running from the project root OR from inside evaluator/
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_here, ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
from smolagents import ToolCallingAgent, tool

LOG_PATH  = "data/output/test_results_log.txt"

# ── Outcome categories ─────────────────────────────────────────────────────────

OUTCOME_LABELS = {
    "SALE":          "Sale finalized",
    "STOCK":         "Insufficient stock",
    "PARSE":         "Parse failure",
    "REJECTED":      "Customer rejected",
    "QUOTE_FAILED":  "Quote generation failed",
    "HALLUCINATION": "Fulfillment failed (hallucination)",
    "UNKNOWN":       "Unknown",
}


def _categorize(outcome: str) -> str:
    o = outcome.lower()
    if o.startswith("sale finalized"):
        return "SALE"
    if o.startswith("insufficient stock"):
        return "STOCK"
    if o.startswith("parse failure"):
        return "PARSE"
    if o.startswith("customer rejected"):
        return "REJECTED"
    if o.startswith("fulfillment failed"):
        return "HALLUCINATION"
    if o.startswith("quote generation failed"):
        return "QUOTE_FAILED"
    return "UNKNOWN"


# ── Log parser ────────────────────────────────────────────────────────────────

# Each log block looks like:
# ============================================================
# Request #3  |  started: 2026-04-16 10:02:01
# ============================================================
#   INVENTORY CHECK     :   4.87s
#   QUOTE               :   2.01s
#   FULFILLMENT         :   1.23s        <- optional
# ------------------------------------------------------------
#   TOTAL               :   8.11s
# ------------------------------------------------------------
#   OUTCOME             : Sale finalized at $240.00
#   REASON              : ...
# ============================================================

_BLOCK_RE = re.compile(
    r"={10,}\s*\n"
    r"Request\s+#(\d+)\s+\|\s+started:\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\n"
    r"={10,}\s*\n"
    r"(.*?)"            # step lines
    r"-{10,}\s*\n"
    r"\s+TOTAL\s+:\s+([\d.]+)s\s*\n"
    r"-{10,}\s*\n"
    r"\s+OUTCOME\s+:\s+(.+?)\s*\n"
    r"\s+REASON\s+:\s+(.+?)\s*\n"
    r"={10,}",
    re.DOTALL,
)

_STEP_RE = re.compile(r"^\s+([\w ]+?)\s+:\s+([\d.]+)s", re.MULTILINE)

_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")


def parse_log_file(path: str) -> list[dict]:
    """Parse test_results_log.txt and return one dict per request block."""
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as f:
        content = f.read()

    entries = []
    for m in _BLOCK_RE.finditer(content):
        request_id  = int(m.group(1))
        started_at  = m.group(2)
        steps_block = m.group(3)
        total_s     = float(m.group(4))
        outcome     = m.group(5).strip()
        reason      = m.group(6).strip()

        steps = {}
        for sm in _STEP_RE.finditer(steps_block):
            step_name = sm.group(1).strip()
            if step_name != "TOTAL":
                steps[step_name] = float(sm.group(2))

        # Extract revenue from outcome string (e.g. "Sale finalized at $240.00")
        price_match = _PRICE_RE.search(outcome)
        revenue = float(price_match.group(1).replace(",", "")) if price_match else 0.0

        entries.append({
            "request_id":  request_id,
            "started_at":  started_at,
            "steps":       steps,
            "total_s":     total_s,
            "outcome":     outcome,
            "category":    _categorize(outcome),
            "reason":      reason,
            "revenue":     revenue,
        })

    return entries


# ── Metric computation ────────────────────────────────────────────────────────

def _stats(values: list[float]) -> dict:
    if not values:
        return {"avg": 0, "min": 0, "max": 0, "p95": 0, "count": 0}
    sorted_v = sorted(values)
    p95_idx  = max(0, int(len(sorted_v) * 0.95) - 1)
    return {
        "avg":   round(statistics.mean(values), 2),
        "min":   round(min(values), 2),
        "max":   round(max(values), 2),
        "p95":   round(sorted_v[p95_idx], 2),
        "count": len(values),
    }


def compute_metrics(entries: list[dict]) -> dict:
    """Derive all evaluation metrics from parsed log entries."""
    if not entries:
        return {"error": "No log entries found — run evaluation.py first."}

    total = len(entries)

    # Outcome breakdown
    breakdown: dict[str, int] = {k: 0 for k in OUTCOME_LABELS}
    for e in entries:
        breakdown[e["category"]] = breakdown.get(e["category"], 0) + 1

    # Latency per step
    step_latencies: dict[str, list[float]] = {}
    total_latencies: list[float] = []
    for e in entries:
        total_latencies.append(e["total_s"])
        for step, dur in e["steps"].items():
            step_latencies.setdefault(step, []).append(dur)

    latency_stats = {step: _stats(vals) for step, vals in step_latencies.items()}
    latency_stats["TOTAL"] = _stats(total_latencies)

    # Revenue
    sales = [e for e in entries if e["category"] == "SALE"]
    revenues = [e["revenue"] for e in sales if e["revenue"] > 0]
    total_revenue = sum(revenues)
    avg_order_value = round(total_revenue / len(revenues), 2) if revenues else 0.0

    # Hallucination count
    hallucinations = breakdown.get("HALLUCINATION", 0)

    return {
        "summary": {
            "total_requests":    total,
            "successful_sales":  breakdown["SALE"],
            "fulfillment_rate":  round(breakdown["SALE"] / total * 100, 1),
            "hallucinations":    hallucinations,
        },
        "outcome_breakdown": {
            OUTCOME_LABELS[k]: v
            for k, v in breakdown.items()
            if v > 0
        },
        "latency_seconds": latency_stats,
        "revenue": {
            "total_revenue":   round(total_revenue, 2),
            "avg_order_value": avg_order_value,
            "sales_count":     len(revenues),
        },
    }


# ── Hard-coded report printer ─────────────────────────────────────────────────

_SEP  = "=" * 60
_LINE = "-" * 60

def print_metrics_report(metrics: dict) -> None:
    """Print a formatted evaluation report to stdout."""
    print()
    print(_SEP)
    print("  PaperTrail Co. — Pipeline Evaluation Report")
    print(_SEP)

    if "error" in metrics:
        print(f"\n  ERROR: {metrics['error']}")
        print()
        return

    s = metrics["summary"]
    print(f"\n  SUMMARY")
    print(_LINE)
    print(f"  Total requests processed : {s['total_requests']}")
    print(f"  Successful sales         : {s['successful_sales']}")
    print(f"  Fulfillment rate         : {s['fulfillment_rate']}%")
    print(f"  Hallucinations detected  : {s['hallucinations']}")

    print(f"\n  OUTCOME BREAKDOWN")
    print(_LINE)
    for label, count in metrics["outcome_breakdown"].items():
        pct = round(count / s["total_requests"] * 100, 1)
        bar = "█" * int(pct / 5)
        print(f"  {label:<35} {count:>3}  ({pct:>5.1f}%)  {bar}")

    print(f"\n  LATENCY (seconds)")
    print(_LINE)
    print(f"  {'Step':<22} {'avg':>6}  {'min':>6}  {'max':>6}  {'p95':>6}  {'n':>4}")
    print(f"  {'-'*22} {'------':>6}  {'------':>6}  {'------':>6}  {'------':>6}  {'----':>4}")
    for step, st in metrics["latency_seconds"].items():
        if st["count"] == 0:
            continue
        print(f"  {step:<22} {st['avg']:>6.2f}  {st['min']:>6.2f}  {st['max']:>6.2f}  {st['p95']:>6.2f}  {st['count']:>4}")

    r = metrics["revenue"]
    print(f"\n  REVENUE")
    print(_LINE)
    print(f"  Total revenue            : ${r['total_revenue']:,.2f}")
    print(f"  Average order value      : ${r['avg_order_value']:,.2f}")
    print(f"  Sales with revenue data  : {r['sales_count']}")

    print()
    print(_SEP)
    print()


# ── LLM evaluation agent ──────────────────────────────────────────────────────

_EVALUATOR_PROMPT = """
You are a senior AI systems auditor evaluating the PaperTrail Co. agentic sales pipeline.

You have one tool: `get_pipeline_metrics`. Call it first to retrieve the evaluation data.

After receiving the metrics, write a structured qualitative report covering:

1. OVERALL ASSESSMENT — one paragraph summarising pipeline health
2. STRENGTHS — bullet points on what the pipeline is doing well
3. WEAKNESSES — bullet points on failure modes and reliability concerns
4. LATENCY ANALYSIS — which stage is the bottleneck and why it matters
5. RECOMMENDATIONS — 3–5 concrete, actionable improvements

Be specific. Reference actual numbers from the metrics.
Produce your report as plain text (no markdown headers, use ALL-CAPS labels as shown above).
End with a single overall score: PIPELINE SCORE: X/10
""".strip()


def build_evaluator_agent(model) -> ToolCallingAgent:
    """Create a ToolCallingAgent wired to the metrics tool."""

    @tool
    def get_pipeline_metrics() -> str:
        """
        Returns the computed evaluation metrics for the most recent batch test run
        as a JSON string. Call this first before writing your analysis.
        """
        entries = parse_log_file(LOG_PATH)
        metrics = compute_metrics(entries)
        return json.dumps(metrics, indent=2)

    return ToolCallingAgent(
        name="pipeline_evaluator",
        tools=[get_pipeline_metrics],
        model=model,
        max_steps=4,
        instructions=_EVALUATOR_PROMPT,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate the PaperTrail Co. agentic sales pipeline results."
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip the LLM qualitative analysis — print hard-coded metrics only.",
    )
    args = parser.parse_args()

    # ── Layer 1: Hard-coded metrics ───────────────────────────────────────────
    entries = parse_log_file(LOG_PATH)
    metrics = compute_metrics(entries)
    print_metrics_report(metrics)

    if args.no_llm or "error" in metrics:
        return

    # ── Layer 2: LLM qualitative analysis ────────────────────────────────────
    load_dotenv()

    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("  [WARN] NVIDIA_API_KEY not set — skipping LLM analysis.")
        print("         Set the key in .env or use --no-llm to suppress this warning.")
        return

    from src.utils.model_wrapper import ResilientOpenAIModel

    model = ResilientOpenAIModel(
        model_id="meta/llama-3.3-70b-instruct",
        api_base="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
        client_kwargs={"timeout": 60},
    )

    print(_SEP)
    print("  LLM Qualitative Analysis")
    print(_SEP)
    print("  Calling evaluation agent...\n")

    agent = build_evaluator_agent(model)
    try:
        analysis = agent.run("Evaluate the PaperTrail Co. pipeline and write your report.")
        print(analysis)
    except Exception as e:
        print(f"  [ERROR] LLM evaluation failed: {e}")

    print()
    print(_SEP)
    print()


if __name__ == "__main__":
    main()
