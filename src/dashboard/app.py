"""Inventory demand and stock-risk operations dashboard.

Run from the project root with: python -m streamlit run src/dashboard/app.py
The UI uses only Streamlit and the Python standard library so it also runs in
the project's constrained Windows environment.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
from collections import defaultdict

import streamlit as st


st.set_page_config(
    page_title="Inventory Intelligence | Control Tower",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)



def build_theme_vars(mode: str) -> str:
    palette = {
        "Light": {
            "bg": "#f4f7f6",
            "surface": "#ffffff",
            "sidebar": "#eef4f1",
            "ink": "#152228",
            "muted": "#5b6a70",
            "line": "#dfe8e3",
            "hover": "#edf4ef",
            "table-hover": "#f6faf7",
            "input": "#ffffff",
            "pill-red": "#9a2a2a",
            "pill-red-bg": "#fee1e1",
            "pill-amber": "#8b5a1e",
            "pill-amber-bg": "#fff0d8",
            "pill-green": "#1d5d40",
            "pill-green-bg": "#dff6eb",
            "pill-purple": "#5a3d92",
            "pill-purple-bg": "#efe8ff",
        },
        "Dark": {
            "bg": "#0d1117",
            "surface": "#171b22",
            "sidebar": "#111821",
            "ink": "#e6edf3",
            "muted": "#a6b3bd",
            "line": "#2a3641",
            "hover": "#1b2330",
            "table-hover": "#1d2a34",
            "input": "#111827",
            "pill-red": "#f9b7b5",
            "pill-red-bg": "#3a1a1d",
            "pill-amber": "#f6c76f",
            "pill-amber-bg": "#483219",
            "pill-green": "#b5e7c6",
            "pill-green-bg": "#183524",
            "pill-purple": "#d7c5ff",
            "pill-purple-bg": "#2b2141",
        },
    }.get(mode, {
        "bg": "#0f1720",
        "surface": "#171f29",
        "sidebar": "#111b24",
        "ink": "#edf5f8",
        "muted": "#a9b7c2",
        "line": "#2a3642",
        "hover": "#1a2632",
        "table-hover": "#1d2d39",
        "input": "#101923",
        "pill-red": "#f9b7b5",
        "pill-red-bg": "#3a1a1d",
        "pill-amber": "#f6c76f",
        "pill-amber-bg": "#483219",
        "pill-green": "#b5e7c6",
        "pill-green-bg": "#183524",
        "pill-purple": "#d7c5ff",
        "pill-purple-bg": "#2b2141",
    })

    return f"""
    --bg:{palette['bg']};
    --surface:{palette['surface']};
    --sidebar:{palette['sidebar']};
    --ink:{palette['ink']};
    --muted:{palette['muted']};
    --line:{palette['line']};
    --hover:{palette['hover']};
    --table-hover:{palette['table-hover']};
    --input:{palette['input']};
    --pill-red:{palette['pill-red']};
    --pill-red-bg:{palette['pill-red-bg']};
    --pill-amber:{palette['pill-amber']};
    --pill-amber-bg:{palette['pill-amber-bg']};
    --pill-green:{palette['pill-green']};
    --pill-green-bg:{palette['pill-green-bg']};
    --pill-purple:{palette['pill-purple']};
    --pill-purple-bg:{palette['pill-purple-bg']};
    """


theme_vars = build_theme_vars("Light")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT_PATH = os.path.join(BASE_DIR, "data", "gold", "latest_risk_snapshot.json")
METRICS_PATH = os.path.join(BASE_DIR, "models", "model_metrics.json")
SALES_PATH = os.path.join(BASE_DIR, "data", "raw", "sales_data.csv")

st.markdown("""
<style>
__THEME_VARS__

html, body, .stApp, [data-testid="stAppViewContainer"] {
    background:var(--bg) !important;
    color:var(--ink) !important;
    font-family:'Segoe UI',sans-serif;
}
[data-testid="stHeader"] { background:var(--bg) !important; }
[data-testid="stSidebar"] {
    background:var(--sidebar) !important;
    border-right:1px solid var(--line);
}
.block-container { padding-top:1.55rem; padding-bottom:2.5rem; max-width:1500px; }
h1,h2,h3,h4,p,label,span,li { color:var(--ink); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
.small-muted, .section-kicker { color:var(--muted) !important; }

[data-testid="stMetric"] {
    background:var(--surface) !important;
    border:1px solid var(--line);
    padding:16px 18px;
    border-radius:14px;
    box-shadow:0 2px 8px #00000012;
}
[data-testid="stMetricLabel"] { color:var(--muted) !important; }
[data-testid="stMetricValue"] { color:var(--ink) !important; }

input, textarea, [data-baseweb="select"] > div {
    background:var(--input) !important;
    color:var(--ink) !important;
    border-color:var(--line) !important;
}
[data-baseweb="popover"], [data-baseweb="menu"] {
    background:var(--surface) !important;
    color:var(--ink) !important;
}
[data-baseweb="menu"] * { color:var(--ink) !important; }

[data-testid="stTabs"] button { color:var(--muted) !important; font-weight:650; }
[data-testid="stTabs"] button[aria-selected="true"] { color:var(--ink) !important; }
[data-testid="stDataFrame"], [data-testid="stExpander"] {
    background:var(--surface) !important;
    border:1px solid var(--line) !important;
    border-radius:12px;
}

.hero {
    background:linear-gradient(115deg,#123d2b,#1e694b 65%,#3c8a62);
    border-radius:18px; padding:25px 29px; color:white; margin:3px 0 20px;
}
.hero h2 { color:white !important; margin:0 0 5px; font-size:1.5rem; }
.hero p { color:#e0eee5 !important; margin:0; font-size:.94rem; }
.eyebrow { font-size:.72rem; text-transform:uppercase; letter-spacing:.12em; opacity:.85; font-weight:700; margin-bottom:8px; }
.panel { background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:17px 19px; }
.pill { border-radius:30px; padding:4px 9px; font-size:.72rem; font-weight:700; white-space:nowrap; }
.risk-high { color:var(--pill-red) !important; background:var(--pill-red-bg); }
.risk-elevated { color:var(--pill-amber) !important; background:var(--pill-amber-bg); }
.risk-low { color:var(--pill-green) !important; background:var(--pill-green-bg); }
.risk-over { color:var(--pill-purple) !important; background:var(--pill-purple-bg); }

.inventory-table-wrap {
    overflow:auto; max-height:540px;
    border:1px solid var(--line); border-radius:12px;
    background:var(--surface);
}
.inventory-table { width:100%; border-collapse:collapse; font-size:13px; white-space:nowrap; }
.inventory-table th, .inventory-table td {
    padding:10px 12px; text-align:left;
    border-bottom:1px solid var(--line); color:var(--ink);
}
.inventory-table th {
    position:sticky; top:0; background:var(--hover);
    color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em;
}
.inventory-table tbody tr:hover { background:var(--table-hover); }
</style>
""".replace("__THEME_VARS__", theme_vars), unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading inventory and sales data…")
def load_snapshot():
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


@st.cache_data(show_spinner="Loading model scorecard…")
def load_metrics():
    with open(METRICS_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner="Reading sales history…")
def load_history(store_id: str, product_id: str):
    rows = []
    with open(SALES_PATH, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("Store ID") == store_id and r.get("Product ID") == product_id:
                rows.append({
                    "date": r["Date"], "demand": float(r["Demand"]),
                    "stock": float(r["Inventory Level"]),
                    "ordered": float(r["Units Ordered"]),
                    "promotion": int(float(r.get("Promotion", 0) or 0)),
                })
    rows.sort(key=lambda x: x["date"])
    return rows


def number(value, digits=0):
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def risk_class(value):
    if value == "HIGH_STOCKOUT_RISK": return "risk-high"
    if value == "ELEVATED_STOCKOUT_RISK": return "risk-elevated"
    if value == "CRITICAL_OVERSTOCK" or value == "SLOW_MOVING": return "risk-over"
    return "risk-low"


def risk_label(value):
    return value.replace("_", " ").title() if value else "—"


def render_table(rows, limit=100):
    if not rows:
        st.info("No products match these filters.")
        return
    columns = ["Store", "SKU", "Category", "On hand", "Incoming", "7d demand", "Net gap", "Cover (d)", "Stock risk", "Velocity", "Recommended action"]
    data = []
    for r in rows[:limit]:
        data.append({
            "Store": r.get("store_id", "—"), "SKU": r.get("product_id", "—"),
            "Category": r.get("category", "—"), "On hand": int(r.get("current_stock", 0)),
            "Incoming": int(r.get("incoming_orders", 0)),
            "7d demand": round(float(r.get("forecast_demand_7d", 0)), 1),
            "Net gap": round(float(r.get("inventory_gap", 0)), 1),
            "Cover (d)": round(float(r.get("days_of_cover", 0)), 1),
            "Stock risk": risk_label(r.get("stockout_risk")),
            "Velocity": risk_label(r.get("overstock_risk")),
            "Recommended action": r.get("status_action", "—").replace("_", " ").title(),
        })
    header = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row[c]))}</td>" for c in columns) + "</tr>" for row in data)
    st.markdown(
        f'<div class="inventory-table-wrap">'
        f'<table class="inventory-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{body}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    if len(rows) > limit:
        st.caption(f"Showing {limit} of {len(rows)} matching products. Narrow the filters to inspect a smaller set.")


def chart(values, mark="line", height=300, encoding=None):
    st.vega_lite_chart({
        "data": {"values": values}, "width": "container", "height": height,
        "mark": mark, "encoding": encoding or {},
    }, width="stretch")


try:
    snapshot = load_snapshot()
    metrics = load_metrics()
except (OSError, json.JSONDecodeError) as exc:
    st.error(f"The dashboard could not load its project data: {exc}")
    st.info("Confirm that the project contains data/gold/latest_risk_snapshot.json and models/model_metrics.json.")
    st.stop()

if not snapshot:
    st.error("The inventory risk snapshot is empty. Generate a risk snapshot from the project pipeline, then refresh this page.")
    st.stop()

snapshot_date = snapshot[0].get("snapshot_date", "Unknown")
stores = sorted({r.get("store_id", "") for r in snapshot if r.get("store_id")})
categories = sorted({r.get("category", "") for r in snapshot if r.get("category")})

st.sidebar.markdown("## 📦 Inventory control tower")
st.sidebar.caption("Demand planning · stock risk · replenishment decisions")
st.sidebar.markdown("---")
store_filter = st.sidebar.selectbox("Store", ["All stores", *stores])
category_filter = st.sidebar.selectbox("Category", ["All categories", *categories])
risk_filter = st.sidebar.selectbox("Stock risk", ["All risk levels", "HIGH_STOCKOUT_RISK", "ELEVATED_STOCKOUT_RISK", "LOW_STOCKOUT_RISK"])
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Forecast horizon**  \n7 days · Spark MLlib Random Forest")
st.sidebar.caption(f"Risk snapshot: {snapshot_date}")
if st.sidebar.button("Refresh project data", use_container_width=True):
    load_snapshot.clear(); load_metrics.clear(); load_history.clear(); st.rerun()

filtered = [r for r in snapshot
            if (store_filter == "All stores" or r.get("store_id") == store_filter)
            and (category_filter == "All categories" or r.get("category") == category_filter)
            and (risk_filter == "All risk levels" or r.get("stockout_risk") == risk_filter)]
high = [r for r in filtered if r.get("stockout_risk") == "HIGH_STOCKOUT_RISK"]
elevated = [r for r in filtered if r.get("stockout_risk") == "ELEVATED_STOCKOUT_RISK"]
overstock = [r for r in filtered if r.get("overstock_risk") in ("CRITICAL_OVERSTOCK", "SLOW_MOVING")]
shortfall = sum(max(0, -float(r.get("inventory_gap", 0))) for r in filtered)
forecast_total = sum(float(r.get("forecast_demand_7d", 0)) for r in filtered)

st.markdown('<div class="hero"><div class="eyebrow">Inventory operations · snapshot ' + html.escape(str(snapshot_date)) + '</div><h2>Know what will run out. Act before it does.</h2><p>Seven-day demand forecasts translated into a prioritized replenishment and excess-stock plan.</p></div>', unsafe_allow_html=True)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("SKUs in view", f"{len(filtered):,}", f"{len({r.get('store_id') for r in filtered})} stores")
k2.metric("Urgent stockouts", f"{len(high):,}", "Forecast exceeds available stock", delta_color="inverse")
k3.metric("Watch list", f"{len(elevated):,}", "Below safety buffer", delta_color="inverse")
k4.metric("7-day demand", f"{forecast_total:,.0f}", "units across selected SKUs")
k5.metric("Uncovered demand", f"{shortfall:,.0f}", "units to replenish", delta_color="inverse")

tab_overview, tab_risk, tab_forecast, tab_actions, tab_model = st.tabs([
    "Overview", "Stock risk", "Forecast explorer", "Replenishment planner", "Model & data"
])

with tab_overview:
    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("Demand by category")
        cats = defaultdict(float)
        for r in filtered: cats[r.get("category", "Other")] += float(r.get("forecast_demand_7d", 0))
        values = [{"category": k, "units": round(v, 1)} for k, v in sorted(cats.items(), key=lambda kv: -kv[1])]
        if values:
            chart(values, mark={"type": "bar", "cornerRadiusEnd": 5, "color": "#27835c"}, height=250,
                  encoding={"x": {"field": "units", "type": "quantitative", "title": "Forecast demand (units)"},
                            "y": {"field": "category", "type": "nominal", "sort": "-x", "title": None},
                            "tooltip": [{"field": "category"}, {"field": "units", "format": ",.1f"}]})
    with right:
        st.subheader("Portfolio stock exposure")
        counts = [{"state": "Urgent", "skus": len(high)}, {"state": "Watch", "skus": len(elevated)},
                  {"state": "Healthy", "skus": max(0, len(filtered) - len(high) - len(elevated))}]
        chart(counts, mark={"type": "arc", "innerRadius": 65, "outerRadius": 105}, height=250,
              encoding={"theta": {"field": "skus", "type": "quantitative"},
                        "color": {"field": "state", "type": "nominal", "scale": {"domain": ["Urgent", "Watch", "Healthy"], "range": ["#c74b43", "#e4a03a", "#45956c"]}},
                        "tooltip": [{"field": "state"}, {"field": "skus"}]})
    st.subheader("Priority queue")
    st.caption("Highest shortfall first. Use the replenishment planner to test order quantities against lead time and safety stock.")
    priority = sorted(filtered, key=lambda r: (0 if r.get("stockout_risk") == "HIGH_STOCKOUT_RISK" else 1 if r.get("stockout_risk") == "ELEVATED_STOCKOUT_RISK" else 2, float(r.get("inventory_gap", 0))))
    render_table(priority, 12)

with tab_risk:
    st.subheader("Stock-out and slow-moving watchlists")
    urgent, slow = st.tabs([f"Replenishment risk · {len(high) + len(elevated)}", f"Excess & slow-moving · {len(overstock)}"])
    with urgent:
        st.markdown("#### Items needing attention")
        st.caption("Risk uses the saved seven-day model forecast and the deterministic inventory policy. Net gap = on-hand + incoming − forecast.")
        risk_rows = sorted([r for r in filtered if r.get("stockout_risk") in ("HIGH_STOCKOUT_RISK", "ELEVATED_STOCKOUT_RISK")], key=lambda r: (0 if r.get("stockout_risk") == "HIGH_STOCKOUT_RISK" else 1, float(r.get("inventory_gap", 0))))
        render_table(risk_rows)
    with slow:
        st.markdown("#### Capital tied up in excess inventory")
        st.caption("High cover signals inventory that may need a purchase pause, markdown, or bundle review.")
        render_table(sorted(overstock, key=lambda r: -float(r.get("days_of_cover", 0))))

with tab_forecast:
    st.subheader("SKU demand and inventory trajectory")
    stores_for_sku = sorted({r.get("store_id") for r in snapshot if r.get("store_id")})
    selected_store = st.selectbox("Choose a store", stores_for_sku, key="forecast_store")
    candidates = [r for r in snapshot if r.get("store_id") == selected_store]
    product_options = sorted({r.get("product_id") for r in candidates if r.get("product_id")})
    selected_product = st.selectbox("Choose a product", product_options, key="forecast_product")
    rec = next((r for r in candidates if r.get("product_id") == selected_product), None)
    if rec:
        hist = load_history(selected_store, selected_product)
        if hist:
            fc, stock, cover, gap = st.columns(4)
            fc.metric("7-day ML forecast", f"{float(rec.get('forecast_demand_7d', 0)):,.1f} units")
            stock.metric("Current on hand", f"{int(rec.get('current_stock', 0)):,} units")
            cover.metric("Days of cover", f"{float(rec.get('days_of_cover', 0)):.1f} days")
            gap.metric("Net inventory gap", f"{float(rec.get('inventory_gap', 0)):+,.1f} units")
            window = st.slider("History window", min_value=30, max_value=min(365, len(hist)), value=min(90, len(hist)), step=15)
            view = hist[-window:]
            series = [{"date": r["date"], "value": r["demand"], "series": "Actual demand"} for r in view]
            daily_forecast = float(rec.get("forecast_demand_7d", 0)) / 7
            last_date = dt.date.fromisoformat(hist[-1]["date"])
            for i in range(1, 8):
                series.append({"date": (last_date + dt.timedelta(days=i)).isoformat(), "value": daily_forecast, "series": "ML forecast · daily avg"})
            chart(series, mark={"type": "line", "point": {"filled": True, "size": 25}}, height=330,
                  encoding={"x": {"field": "date", "type": "temporal", "title": "Date", "axis": {"labelAngle": -30}},
                            "y": {"field": "value", "type": "quantitative", "title": "Units per day"},
                            "color": {"field": "series", "type": "nominal", "scale": {"domain": ["Actual demand", "ML forecast · daily avg"], "range": ["#4787b5", "#e18a38"]}},
                            "tooltip": [{"field": "date", "type": "temporal"}, {"field": "value", "format": ",.1f"}, {"field": "series"}]})
            stock_series = [{"date": r["date"], "value": r["stock"]} for r in view]
            st.markdown("#### Inventory position history")
            chart(stock_series, mark={"type": "area", "color": "#55a27a", "opacity": 0.3, "line": {"color": "#35835d"}}, height=180,
                  encoding={"x": {"field": "date", "type": "temporal", "title": None}, "y": {"field": "value", "type": "quantitative", "title": "On-hand units"}, "tooltip": [{"field": "date", "type": "temporal"}, {"field": "value", "format": ",.0f"}]})
            st.info(f"**{rec.get('status_action', '—').replace('_', ' ').title()}** · {rec.get('recommendation', 'No recommendation available.')}")
            st.caption("The orange segment is the 7-day model total spread evenly as a daily reference; it is not a separately trained daily forecast.")
        else:
            st.warning("No matching historical sales rows were found for this store and product.")

with tab_actions:
    st.subheader("Replenishment planner")
    st.caption("Try an order quantity and lead time to see whether the item remains covered through delivery. This is a planning scenario; it does not place a purchase order.")
    action_store = st.selectbox("Store", stores_for_sku, key="planner_store")
    action_candidates = [r for r in snapshot if r.get("store_id") == action_store]
    action_product = st.selectbox("Product", sorted(r["product_id"] for r in action_candidates), key="planner_product")
    ar = next(r for r in action_candidates if r.get("product_id") == action_product)
    a, b, c = st.columns(3)
    lead_days = a.number_input("Supplier lead time (days)", min_value=1, max_value=60, value=7)
    order_qty = b.number_input("Proposed order (units)", min_value=0, max_value=100000, value=max(0, int(-min(float(ar.get("inventory_gap", 0)), 0))))
    safety_pct = c.slider("Safety buffer", min_value=0, max_value=50, value=15, format="%d%%")
    daily = float(ar.get("forecast_demand_7d", 0)) / 7
    need_by_delivery = daily * lead_days * (1 + safety_pct / 100)
    available_at_delivery = float(ar.get("current_stock", 0)) + float(ar.get("incoming_orders", 0)) + order_qty
    buffer_after_delivery = available_at_delivery - need_by_delivery
    p1, p2, p3 = st.columns(3)
    p1.metric("Demand through lead time + buffer", f"{need_by_delivery:,.1f} units")
    p2.metric("Projected available", f"{available_at_delivery:,.0f} units")
    p3.metric("Position after lead time", f"{buffer_after_delivery:+,.1f} units", delta_color="normal")
    if buffer_after_delivery < 0:
        st.error(f"Projected shortfall of {abs(buffer_after_delivery):,.1f} units before/through replenishment. Expedite or increase the order.")
    elif float(ar.get("days_of_cover", 0)) > 45:
        st.warning("This item is already classified as critical overstock. Review whether this proposed purchase should be delayed.")
    else:
        st.success("Proposed quantity covers forecast demand through the supplier lead time and selected safety buffer.")
    st.markdown("#### Selected SKU recommendation")
    render_table([ar], 1)

with tab_model:
    st.subheader("Forecast model & data confidence")
    val = metrics.get("validation_comparison", {})
    test = metrics.get("test_performance", {})
    meta1, meta2, meta3, meta4 = st.columns(4)
    meta1.metric("Model", "Random Forest")
    meta2.metric("Validation WAPE", f"{val.get('Random_Forest_ML', {}).get('WAPE', '—')}%")
    meta3.metric("Held-out test WAPE", f"{test.get('WAPE', '—')}%")
    meta4.metric("Forecast horizon", "7 days")
    comparison = []
    for key, label in [("Baseline_Naive_Lag1", "Naive lag-1"), ("Baseline_Rolling_7d", "Rolling 7-day"), ("Random_Forest_ML", "Spark MLlib random forest")]:
        if key in val:
            comparison.extend([{"model": label, "metric": "WAPE", "value": float(val[key]["WAPE"])},
                               {"model": label, "metric": "MAE", "value": float(val[key]["MAE"])}])
    st.markdown("#### Validation benchmarks")
    chart(comparison, mark={"type": "bar", "cornerRadiusEnd": 4}, height=270,
          encoding={"x": {"field": "value", "type": "quantitative", "title": "Error (WAPE % or MAE units)"},
                    "y": {"field": "model", "type": "nominal", "sort": "-x", "title": None},
                    "color": {"field": "metric", "type": "nominal", "scale": {"domain": ["WAPE", "MAE"], "range": ["#297c58", "#86ad99"]}},
                    "tooltip": [{"field": "model"}, {"field": "metric"}, {"field": "value", "format": ",.2f"}]})
    splits = metrics.get("chronological_splits", {})
    st.markdown("#### Evaluation periods")
    s1, s2, s3 = st.columns(3)
    s1.markdown(f"**Training**  \n{splits.get('train_period', '—')}")
    s2.markdown(f"**Validation**  \n{splits.get('val_period', '—')}")
    s3.markdown(f"**Held-out test**  \n{splits.get('test_period', '—')}")
    with st.expander("Features supplied to the model"):
        st.write(", ".join(metrics.get("features", [])))
    st.markdown("#### Load new sales history")
    uploaded = st.file_uploader("Upload a CSV to inspect its coverage", type=["csv"], help="Expected columns include Date, Store ID, Product ID, and Demand.")
    if uploaded:
        try:
            rows = list(csv.DictReader(uploaded.getvalue().decode("utf-8-sig").splitlines()))
            required = {"Date", "Store ID", "Product ID", "Demand"}
            if not rows or not required.issubset(rows[0]):
                st.error("This CSV is missing required columns: Date, Store ID, Product ID, Demand.")
            else:
                st.success(f"Loaded {len(rows):,} rows for review · {len({r['Product ID'] for r in rows})} products · {min(r['Date'] for r in rows)} to {max(r['Date'] for r in rows)}.")
                st.caption("This preview does not retrain or replace the saved Spark model. Run the project's feature engineering and training pipeline to publish an updated model and risk snapshot.")
        except (UnicodeDecodeError, csv.Error, KeyError) as exc:
            st.error(f"Could not read this CSV: {exc}")

st.markdown("---")
st.caption("Inventory Intelligence · Forecasts and risk flags use the latest saved project snapshot. Refresh the snapshot after running the scoring pipeline to update recommendations.")
