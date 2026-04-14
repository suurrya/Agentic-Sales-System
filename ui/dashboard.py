import os
import pandas as pd
from nicegui import ui

OLAP_PATH = "data/output/olap_database.csv"
OLTP_PATH = "data/output/oltp_database.csv"
FAILURES_PATH = "data/output/agent_failures.jsonl"


def load_data():
    olap = pd.read_csv(OLAP_PATH, parse_dates=["request_date"])
    oltp = pd.read_csv(OLTP_PATH, parse_dates=["timestamp"])
    oltp["is_fulfilled"] = oltp["is_fulfilled"].astype(bool)
    return olap, oltp


try:
    olap, oltp = load_data()
    load_error = None
except FileNotFoundError as e:
    olap, oltp = pd.DataFrame(), pd.DataFrame()
    load_error = str(e)

# ── Derived metrics ───────────────────────────────────────────────────────────
if not oltp.empty:
    total_requests = len(oltp)
    fulfilled = int(oltp["is_fulfilled"].sum())
    fulfillment_rate = fulfilled / total_requests * 100
    total_revenue = oltp.loc[oltp["is_fulfilled"], "total_value"].sum()
    latest_cash = float(olap["cash_balance"].iloc[-1]) if not olap.empty else 0.0
    latest_inventory = float(olap["inventory_value"].iloc[-1]) if not olap.empty else 0.0
else:
    total_requests = fulfilled = 0
    fulfillment_rate = total_revenue = latest_cash = latest_inventory = 0.0


# ── Page layout ───────────────────────────────────────────────────────────────
ui.page_title("Munder Difflin Dashboard")

with ui.header().classes("bg-blue-800 text-white px-6 py-3 flex items-center gap-3"):
    ui.icon("store").classes("text-2xl")
    ui.label("Munder Difflin — Sales Pipeline Dashboard").classes("text-xl font-semibold")

if load_error:
    with ui.card().classes("m-6 w-full bg-red-50 border border-red-300"):
        ui.label(f"Could not load output files. Run python main.py first.").classes("text-red-700 font-medium")
        ui.label(load_error).classes("text-red-500 text-sm font-mono")
else:
    # ── KPI cards ─────────────────────────────────────────────────────────────
    with ui.row().classes("w-full gap-4 px-6 pt-6 flex-wrap"):
        for label, value in [
            ("Total Requests", str(total_requests)),
            ("Fulfilled", str(fulfilled)),
            ("Fulfillment Rate", f"{fulfillment_rate:.1f}%"),
            ("Total Revenue", f"${total_revenue:,.2f}"),
            ("Cash Balance", f"${latest_cash:,.2f}"),
            ("Inventory Value", f"${latest_inventory:,.2f}"),
        ]:
            with ui.card().classes("flex-1 min-w-[150px] text-center shadow-md"):
                ui.label(value).classes("text-3xl font-bold text-blue-700")
                ui.label(label).classes("text-sm text-gray-500 mt-1")

    ui.separator().classes("mx-6 my-4")

    # ── Charts row 1: Cash balance & total assets over time ───────────────────
    with ui.row().classes("w-full gap-6 px-6 flex-wrap"):
        with ui.card().classes("flex-1 min-w-[300px] shadow-md"):
            ui.label("Cash Balance Over Time").classes("text-lg font-semibold mb-2")
            dates = olap["request_date"].dt.strftime("%b %d").tolist()
            cash_vals = olap["cash_balance"].tolist()
            ui.echart({
                "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 45}},
                "yAxis": {"type": "value"},
                "series": [{"type": "line", "data": cash_vals, "smooth": True,
                            "itemStyle": {"color": "#1d4ed8"}, "areaStyle": {"opacity": 0.15}}],
                "tooltip": {"trigger": "axis"},
                "grid": {"containLabel": True},
            }).classes("w-full h-64")

        with ui.card().classes("flex-1 min-w-[300px] shadow-md"):
            ui.label("Total Assets Over Time").classes("text-lg font-semibold mb-2")
            total_assets = (olap["cash_balance"] + olap["inventory_value"]).tolist()
            ui.echart({
                "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 45}},
                "yAxis": {"type": "value"},
                "series": [{"type": "line", "data": total_assets, "smooth": True,
                            "itemStyle": {"color": "#16a34a"}, "areaStyle": {"opacity": 0.15}}],
                "tooltip": {"trigger": "axis"},
                "grid": {"containLabel": True},
            }).classes("w-full h-64")

    # ── Charts row 2: Fulfillment by type & revenue by event ─────────────────
    with ui.row().classes("w-full gap-6 px-6 mt-4 flex-wrap"):
        with ui.card().classes("flex-1 min-w-[300px] shadow-md"):
            ui.label("Fulfillment Rate by Customer Type").classes("text-lg font-semibold mb-2")
            by_type = (
                oltp.groupby("customer_type")["is_fulfilled"]
                .agg(fulfilled="sum", total="count")
                .assign(rate=lambda df: (df["fulfilled"] / df["total"] * 100).round(1))
                .reset_index()
            )
            ui.echart({
                "xAxis": {"type": "value", "max": 100,
                          "axisLabel": {"formatter": "{value}%"}},
                "yAxis": {"type": "category", "data": by_type["customer_type"].tolist()},
                "series": [{"type": "bar", "data": by_type["rate"].tolist(),
                            "itemStyle": {"color": "#7c3aed"}}],
                "tooltip": {"trigger": "axis", "formatter": "{b}: {c}%"},
                "grid": {"containLabel": True},
            }).classes("w-full h-64")

        with ui.card().classes("flex-1 min-w-[300px] shadow-md"):
            ui.label("Revenue by Event Type").classes("text-lg font-semibold mb-2")
            by_event = (
                oltp.loc[oltp["is_fulfilled"]]
                .groupby("event")["total_value"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            ui.echart({
                "xAxis": {"type": "category", "data": by_event["event"].tolist(),
                          "axisLabel": {"rotate": 30}},
                "yAxis": {"type": "value"},
                "series": [{"type": "bar", "data": by_event["total_value"].tolist(),
                            "itemStyle": {"color": "#ea580c"}}],
                "tooltip": {"trigger": "axis"},
                "grid": {"containLabel": True},
            }).classes("w-full h-64")

    # ── Charts row 3: Items checked vs fulfilled ──────────────────────────────
    with ui.row().classes("w-full gap-6 px-6 mt-4 flex-wrap"):
        with ui.card().classes("flex-1 min-w-[300px] shadow-md"):
            ui.label("Items Checked vs Fulfilled (first 20 requests)").classes("text-lg font-semibold mb-2")
            sample = oltp.head(20)
            req_ids = [str(r) for r in sample["request_id"].tolist()]
            ui.echart({
                "xAxis": {"type": "category", "data": req_ids},
                "yAxis": {"type": "value"},
                "legend": {"data": ["Checked", "Fulfilled"]},
                "series": [
                    {"name": "Checked", "type": "bar", "data": sample["items_checked"].tolist(),
                     "itemStyle": {"color": "#0891b2"}},
                    {"name": "Fulfilled", "type": "bar", "data": sample["items_fulfilled"].tolist(),
                     "itemStyle": {"color": "#16a34a"}},
                ],
                "tooltip": {"trigger": "axis"},
                "grid": {"containLabel": True},
            }).classes("w-full h-64")

        with ui.card().classes("flex-1 min-w-[300px] shadow-md"):
            ui.label("Recent Fulfilled Orders").classes("text-lg font-semibold mb-2")
            recent = (
                oltp[oltp["is_fulfilled"]][
                    ["request_id", "customer_type", "event", "total_value", "timestamp"]
                ]
                .sort_values("timestamp", ascending=False)
                .head(8)
                .reset_index(drop=True)
            )
            columns = [
                {"name": "request_id", "label": "Request", "field": "request_id"},
                {"name": "customer_type", "label": "Customer", "field": "customer_type"},
                {"name": "event", "label": "Event", "field": "event"},
                {"name": "total_value", "label": "Value ($)", "field": "total_value"},
            ]
            rows = recent.to_dict("records")
            for r in rows:
                r["total_value"] = f"{r['total_value']:.2f}"
                r["timestamp"] = str(r["timestamp"])[:19]
            ui.table(columns=columns, rows=rows).classes("w-full text-sm")

    # ── Agent failure log ─────────────────────────────────────────────────────
    if os.path.exists(FAILURES_PATH):
        ui.separator().classes("mx-6 my-4")
        with ui.expansion("Agent Failure Log", icon="warning").classes("mx-6"):
            failures = pd.read_json(FAILURES_PATH, lines=True)
            if not failures.empty:
                with ui.row().classes("gap-6 mb-4"):
                    with ui.card().classes("text-center px-6 py-3"):
                        ui.label(str(len(failures))).classes("text-2xl font-bold text-red-600")
                        ui.label("Total Failures").classes("text-sm text-gray-500")
                    with ui.card().classes("text-center px-6 py-3"):
                        ui.label(failures["agent"].value_counts().idxmax()).classes("text-lg font-bold text-orange-600")
                        ui.label("Most Failing Agent").classes("text-sm text-gray-500")
                columns = [
                    {"name": c, "label": c.replace("_", " ").title(), "field": c}
                    for c in ["timestamp", "agent", "request_id", "attempt", "error_type", "error_message"]
                ]
                rows = failures.sort_values("timestamp", ascending=False).head(20).to_dict("records")
                ui.table(columns=columns, rows=rows).classes("w-full text-sm")
            else:
                ui.label("No agent failures recorded.").classes("text-green-600")

ui.run(title="Munder Difflin Dashboard", port=8080)
