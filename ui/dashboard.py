"""
ui/dashboard.py
===============
PaperTrail Co. — Manager Dashboard (port 8081).

Pages
-----
  /            OLAP Analytics dashboard — financial charts from CSV + live DB
  /live        Live OLTP feed — SQLite transactions, auto-refreshes every 5 s
  /analytics   Batch analytics — outcome breakdown, fulfillment, revenue charts

Run
---
    python ui/dashboard.py

This app is for the manager only. Customers use ui/app.py (port 8080).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from nicegui import ui

from src.database.database import db_engine

OLAP_PATH     = "data/output/olap_database.csv"
OLTP_PATH     = "data/output/oltp_database.csv"
FAILURES_PATH = "data/output/agent_failures.jsonl"

BRAND = "bg-teal-800"


# ── Shared components ─────────────────────────────────────────────────────────

def nav_bar():
    with ui.header().classes(f"{BRAND} text-white px-6 py-3 flex items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("admin_panel_settings").classes("text-2xl")
            with ui.column().classes("gap-0"):
                ui.label("PaperTrail Co. — Manager").classes("text-xl font-bold leading-tight")
                ui.label("Internal dashboard — staff only").classes(
                    "text-xs text-teal-300 leading-tight"
                )
        with ui.row().classes("gap-6"):
            ui.link("Dashboard", "/").classes(
                "text-white hover:text-teal-200 font-medium text-sm"
            )
            ui.link("Live Feed", "/live").classes(
                "text-white hover:text-teal-200 font-medium text-sm"
            )
            ui.link("Analytics", "/analytics").classes(
                "text-white hover:text-teal-200 font-medium text-sm"
            )


def kpi_card(value: str, label: str, color: str = "text-teal-700"):
    with ui.card().classes("flex-1 min-w-[160px] text-center shadow"):
        ui.label(value).classes(f"text-3xl font-bold {color}")
        ui.label(label).classes("text-xs text-gray-500 mt-1 uppercase tracking-wide")


# ── OLAP data helpers ─────────────────────────────────────────────────────────

def _categorize(resp: str) -> str:
    if not isinstance(resp, str):
        return "Unknown"
    r = resp.lower()
    if "sale finalized"        in r: return "Sale Finalized"
    if "insufficient stock"    in r: return "Insufficient Stock"
    if "rejected"              in r: return "Customer Rejected"
    if "could not understand"  in r: return "Parse Failure"
    if "quote generation"      in r: return "Quote Failed"
    if "hallucination"         in r: return "Hallucination"
    if "stock reset"           in r: return "Stock Reset"
    return "Other"

_OUTCOME_COLORS = {
    "Sale Finalized":    "#16a34a",
    "Insufficient Stock":"#f59e0b",
    "Customer Rejected": "#ea580c",
    "Parse Failure":     "#dc2626",
    "Quote Failed":      "#7c3aed",
    "Hallucination":     "#be123c",
    "Stock Reset":       "#0d9488",
    "Other":             "#6b7280",
}


def _load_olap():
    df = pd.read_csv(OLAP_PATH)
    df["request_date"] = pd.to_datetime(df["request_date"], errors="coerce")
    real = df[df["request_id"].astype(str) != "SYSTEM"].copy()
    real["category"] = real["response"].apply(_categorize)
    real["is_fulfilled"] = real["category"] == "Sale Finalized"
    return df, real


def _load_oltp():
    df = pd.read_csv(OLTP_PATH, parse_dates=["timestamp"])
    df["is_fulfilled"] = df["is_fulfilled"].astype(str).str.lower().isin(["true", "1"])
    return df


# ── Page 1: OLAP Dashboard (/) ────────────────────────────────────────────────

@ui.page("/")
def dashboard_page():
    nav_bar()
    ui.page_title("PaperTrail Co. — Dashboard")

    with ui.column().classes("w-full px-6 py-6 gap-5"):
        ui.label("Analytics Dashboard").classes("text-2xl font-bold text-gray-800")
        ui.label("Financial overview from web portal orders.").classes("text-gray-500 text-sm")

        try:
            olap, real = _load_olap()
        except Exception as e:
            with ui.card().classes("bg-amber-50 border border-amber-300 w-full p-4"):
                ui.label(
                    "No OLAP data yet. Submit orders via the customer portal (ui/app.py)."
                ).classes("text-amber-700 text-sm")
            return

        if real.empty:
            with ui.card().classes("bg-gray-50 border border-gray-200 w-full p-8 text-center"):
                ui.icon("bar_chart").classes("text-5xl text-gray-300")
                ui.label("No requests recorded yet.").classes("text-xl font-semibold text-gray-500 mt-2")
            return

        # ── KPI cards ─────────────────────────────────────────────────────────
        total    = len(real)
        fulfilled = int(real["is_fulfilled"].sum())
        rate     = fulfilled / total * 100 if total else 0.0
        latest_cash = float(olap["cash_balance"].iloc[-1])
        latest_inv  = float(olap["inventory_value"].iloc[-1])

        with ui.row().classes("w-full gap-4 flex-wrap"):
            kpi_card(str(total),            "Total Requests")
            kpi_card(str(fulfilled),         "Sales Completed",   "text-green-700")
            kpi_card(f"{rate:.1f}%",         "Fulfillment Rate",  "text-purple-700")
            kpi_card(f"${latest_cash:,.2f}", "Cash Balance",      "text-teal-700")
            kpi_card(f"${latest_inv:,.2f}",  "Inventory Value",   "text-blue-700")
            kpi_card(f"${latest_cash + latest_inv:,.2f}", "Total Assets", "text-gray-700")

        ui.separator().classes("my-1")

        # ── Time series: cash + inventory ────────────────────────────────────
        chart_df = olap.dropna(subset=["request_date"]).sort_values("request_date")
        dates    = chart_df["request_date"].dt.strftime("%b %d").tolist()

        with ui.row().classes("w-full gap-6 flex-wrap"):
            with ui.card().classes("flex-1 min-w-[280px] shadow"):
                ui.label("Cash Balance Over Time").classes("text-base font-semibold mb-2")
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "xAxis":   {"type": "category", "data": dates,
                                "axisLabel": {"rotate": 45, "fontSize": 10}},
                    "yAxis":   {"type": "value"},
                    "series":  [{"type": "line", "data": chart_df["cash_balance"].tolist(),
                                 "smooth": True, "itemStyle": {"color": "#0d9488"},
                                 "areaStyle": {"opacity": 0.12}}],
                    "grid":    {"containLabel": True, "left": 10, "right": 10},
                }).classes("w-full h-56")

            with ui.card().classes("flex-1 min-w-[280px] shadow"):
                ui.label("Inventory Value Over Time").classes("text-base font-semibold mb-2")
                ui.echart({
                    "tooltip": {"trigger": "axis"},
                    "xAxis":   {"type": "category", "data": dates,
                                "axisLabel": {"rotate": 45, "fontSize": 10}},
                    "yAxis":   {"type": "value"},
                    "series":  [{"type": "line", "data": chart_df["inventory_value"].tolist(),
                                 "smooth": True, "itemStyle": {"color": "#0284c7"},
                                 "areaStyle": {"opacity": 0.12}}],
                    "grid":    {"containLabel": True, "left": 10, "right": 10},
                }).classes("w-full h-56")

        # ── Outcome breakdown + recent requests ───────────────────────────────
        outcome_counts = real["category"].value_counts()
        pie_data = [
            {"name": k, "value": int(v),
             "itemStyle": {"color": _OUTCOME_COLORS.get(k, "#6b7280")}}
            for k, v in outcome_counts.items()
        ]

        with ui.row().classes("w-full gap-6 flex-wrap mt-2"):
            with ui.card().classes("flex-1 min-w-[280px] shadow"):
                ui.label("Outcome Breakdown").classes("text-base font-semibold mb-2")
                ui.echart({
                    "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                    "legend":  {"orient": "vertical", "left": "left", "textStyle": {"fontSize": 11}},
                    "series":  [{"type": "pie", "radius": ["35%", "65%"],
                                 "data": pie_data, "label": {"formatter": "{b}\n{d}%"}}],
                }).classes("w-full h-56")

            with ui.card().classes("flex-1 min-w-[280px] shadow"):
                ui.label("Recent Requests").classes("text-base font-semibold mb-2")
                recent = (
                    real[["request_id", "request_date", "cash_balance", "category", "response"]]
                    .sort_values("request_date", ascending=False).head(8)
                )
                rows = recent.to_dict("records")
                for r in rows:
                    r["request_date"] = str(r["request_date"])[:10]
                    r["cash_balance"] = f"${float(r['cash_balance']):,.2f}"
                ui.table(
                    columns=[
                        {"name": "request_id",   "label": "ID",       "field": "request_id"},
                        {"name": "request_date", "label": "Date",     "field": "request_date"},
                        {"name": "category",     "label": "Outcome",  "field": "category"},
                        {"name": "cash_balance", "label": "Cash",     "field": "cash_balance"},
                    ],
                    rows=rows,
                ).classes("w-full text-sm")


# ── Page 2: Live OLTP Feed (/live) ────────────────────────────────────────────

@ui.page("/live")
def live_page():
    nav_bar()
    ui.page_title("PaperTrail Co. — Live Feed")

    with ui.column().classes("w-full px-6 py-6 gap-4"):
        with ui.row().classes("items-center gap-3"):
            ui.label("Live Transaction Feed").classes("text-2xl font-bold text-gray-800")
            ui.badge("LIVE", color="red").classes("text-xs font-bold")
            ui.label("· auto-refreshes every 5 s").classes("text-gray-400 text-xs")

        kpi_row   = ui.row().classes("w-full gap-4 flex-wrap")
        table_wrap = ui.column().classes("w-full")

        def refresh():
            kpi_row.clear()
            table_wrap.clear()

            try:
                txns = pd.read_sql(
                    "SELECT * FROM transactions ORDER BY id DESC LIMIT 200", db_engine
                )
            except Exception:
                with table_wrap:
                    ui.label(
                        "Database not initialised yet — run python evaluator/evaluation.py first."
                    ).classes("text-gray-400 text-sm")
                return

            if txns.empty:
                with table_wrap:
                    ui.label("No transactions recorded yet.").classes("text-gray-400 text-sm")
                return

            sales     = txns[(txns["transaction_type"] == "sales") & txns["item_name"].notna()]
            orders    = txns[txns["transaction_type"] == "stock_orders"]
            total_rev = float(sales["price"].sum())
            avg_sale  = float(sales["price"].mean()) if not sales.empty else 0.0

            with kpi_row:
                kpi_card(str(len(txns)),        "Total Transactions")
                kpi_card(str(len(sales)),        "Sales Orders",        "text-green-700")
                kpi_card(str(len(orders)),       "Stock Orders",        "text-blue-700")
                kpi_card(f"${total_rev:,.2f}",   "Total Sales Revenue", "text-teal-700")
                kpi_card(f"${avg_sale:,.2f}",    "Avg Sale Value",      "text-purple-700")

            with table_wrap:
                with ui.card().classes("w-full shadow"):
                    ui.label("Recent Transactions").classes("text-base font-semibold mb-2")
                    display = txns.copy()
                    display["price"]     = display["price"].apply(
                        lambda x: f"${x:,.2f}" if pd.notna(x) else "—"
                    )
                    display["units"]     = display["units"].apply(
                        lambda x: f"{int(x):,}" if pd.notna(x) else "—"
                    )
                    display["item_name"] = display["item_name"].fillna("—")
                    ui.table(
                        columns=[
                            {"name": "id",               "label": "ID",    "field": "id", "sortable": True},
                            {"name": "item_name",        "label": "Item",  "field": "item_name"},
                            {"name": "transaction_type", "label": "Type",  "field": "transaction_type"},
                            {"name": "units",            "label": "Units", "field": "units"},
                            {"name": "price",            "label": "Price", "field": "price"},
                            {"name": "transaction_date", "label": "Date",  "field": "transaction_date"},
                        ],
                        rows=display.to_dict("records"),
                        pagination={"rowsPerPage": 20},
                    ).classes("w-full text-sm")

        refresh()
        ui.timer(5.0, refresh)


# ── Page 3: Batch Analytics (/analytics) ──────────────────────────────────────

@ui.page("/analytics")
def analytics_page():
    nav_bar()
    ui.page_title("PaperTrail Co. — Analytics")

    with ui.column().classes("w-full px-6 py-6 gap-5"):
        ui.label("Batch Analytics").classes("text-2xl font-bold text-gray-800")
        ui.label(
            "Aggregated metrics from batch evaluation runs and web portal orders."
        ).classes("text-gray-500 text-sm")

        # ── Live DB KPIs ──────────────────────────────────────────────────────
        with ui.row().classes("w-full gap-4 flex-wrap"):
            try:
                cash = float(pd.read_sql(
                    "SELECT COALESCE(SUM(CASE WHEN transaction_type='sales' THEN price "
                    "ELSE -price END), 0) AS cash FROM transactions",
                    db_engine,
                ).iloc[0]["cash"])
                sales_count = int(pd.read_sql(
                    "SELECT COUNT(*) AS n FROM transactions "
                    "WHERE transaction_type='sales' AND item_name IS NOT NULL",
                    db_engine,
                ).iloc[0]["n"])
                kpi_card(f"${cash:,.2f}", "Live Cash Balance",   "text-teal-700")
                kpi_card(str(sales_count), "Sales Transactions", "text-blue-700")
            except Exception:
                pass

            oltp = pd.DataFrame()
            try:
                oltp = _load_oltp()
                total_req = len(oltp)
                fulfilled = int(oltp["is_fulfilled"].sum())
                rate      = fulfilled / total_req * 100 if total_req else 0
                rev       = float(oltp.loc[oltp["is_fulfilled"], "total_value"].sum())
                kpi_card(str(total_req),   "Web Requests",      )
                kpi_card(f"{rate:.1f}%",   "Fulfillment Rate",  "text-purple-700")
                kpi_card(f"${rev:,.2f}",   "Web Revenue",       "text-green-700")
            except Exception:
                pass

        ui.separator().classes("my-1")

        # ── OLTP fulfillment charts ───────────────────────────────────────────
        if not oltp.empty and "customer_type" in oltp.columns:
            with ui.row().classes("w-full gap-6 flex-wrap"):
                with ui.card().classes("flex-1 min-w-[280px] shadow"):
                    ui.label("Fulfillment Rate by Customer Type").classes(
                        "text-base font-semibold mb-2"
                    )
                    by_type = (
                        oltp.groupby("customer_type")["is_fulfilled"]
                        .agg(fulfilled="sum", total="count")
                        .assign(rate=lambda df: (df["fulfilled"] / df["total"] * 100).round(1))
                        .reset_index()
                    )
                    ui.echart({
                        "tooltip": {"trigger": "axis", "formatter": "{b}: {c}%"},
                        "xAxis":   {"type": "value", "max": 100,
                                    "axisLabel": {"formatter": "{value}%"}},
                        "yAxis":   {"type": "category",
                                    "data": by_type["customer_type"].tolist()},
                        "series":  [{"type": "bar", "data": by_type["rate"].tolist(),
                                     "itemStyle": {"color": "#7c3aed"}}],
                        "grid":    {"containLabel": True, "left": 10, "right": 10},
                    }).classes("w-full h-56")

                if oltp["is_fulfilled"].any():
                    by_event = (
                        oltp.loc[oltp["is_fulfilled"]]
                        .groupby("event")["total_value"]
                        .sum().sort_values(ascending=False).reset_index()
                    )
                    with ui.card().classes("flex-1 min-w-[280px] shadow"):
                        ui.label("Revenue by Event Type").classes("text-base font-semibold mb-2")
                        ui.echart({
                            "tooltip": {"trigger": "axis"},
                            "xAxis":   {"type": "category",
                                        "data": by_event["event"].tolist(),
                                        "axisLabel": {"rotate": 30, "fontSize": 10}},
                            "yAxis":   {"type": "value"},
                            "series":  [{"type": "bar", "data": by_event["total_value"].tolist(),
                                         "itemStyle": {"color": "#ea580c"}}],
                            "grid":    {"containLabel": True, "left": 10, "right": 10},
                        }).classes("w-full h-56")

        # ── Live top sellers ──────────────────────────────────────────────────
        with ui.card().classes("w-full shadow"):
            ui.label("Top Selling Products (Live DB)").classes("text-base font-semibold mb-2")
            try:
                top = pd.read_sql(
                    "SELECT item_name, SUM(units) as units_sold, SUM(price) as revenue "
                    "FROM transactions "
                    "WHERE transaction_type='sales' AND item_name IS NOT NULL "
                    "GROUP BY item_name ORDER BY revenue DESC LIMIT 10",
                    db_engine,
                )
                if top.empty:
                    ui.label("No sales recorded yet.").classes("text-gray-400 text-sm")
                else:
                    top["revenue"]    = top["revenue"].apply(lambda x: f"${x:,.2f}")
                    top["units_sold"] = top["units_sold"].apply(lambda x: f"{int(x):,}")
                    ui.table(
                        columns=[
                            {"name": "item_name",  "label": "Product",    "field": "item_name"},
                            {"name": "units_sold", "label": "Units Sold", "field": "units_sold"},
                            {"name": "revenue",    "label": "Revenue",    "field": "revenue"},
                        ],
                        rows=top.to_dict("records"),
                    ).classes("w-full text-sm")
            except Exception as exc:
                ui.label(f"Could not load sales data: {exc}").classes("text-red-500 text-sm")

        # ── Agent failure log ─────────────────────────────────────────────────
        if os.path.exists(FAILURES_PATH):
            ui.separator().classes("my-2")
            with ui.expansion("Agent Failure Log", icon="warning").classes("w-full"):
                import json as _json
                _decoder = _json.JSONDecoder()
                with open(FAILURES_PATH) as _f:
                    _raw = _f.read()
                _records, _pos = [], 0
                while _pos < len(_raw):
                    _pos += len(_raw[_pos:]) - len(_raw[_pos:].lstrip())
                    if _pos >= len(_raw):
                        break
                    _obj, _eaten = _decoder.raw_decode(_raw, _pos)
                    _records.append(_obj)
                    _pos = _eaten
                failures = pd.DataFrame(_records)
                if not failures.empty:
                    with ui.row().classes("gap-6 mb-4"):
                        kpi_card(str(len(failures)), "Total Failures", "text-red-600")
                        kpi_card(
                            failures["agent"].value_counts().idxmax(),
                            "Most Failing Agent", "text-orange-600"
                        )
                    ui.table(
                        columns=[
                            {"name": c, "label": c.replace("_", " ").title(), "field": c}
                            for c in ["timestamp", "agent", "request_id",
                                      "attempt", "error_type", "error_message"]
                        ],
                        rows=failures.sort_values("timestamp", ascending=False)
                                     .head(20).to_dict("records"),
                    ).classes("w-full text-sm")
                else:
                    ui.label("No agent failures recorded.").classes("text-green-600")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="PaperTrail Co. — Manager",
        port=8081,
        favicon="🗂️",
        dark=False,
        show=False,
        reconnect_timeout=600,
    )
