"""
Inventory Intelligence Dashboard  –  Streamlit front-end
=========================================================
Data sources (all real, pre-computed by pipeline):
  • data/gold/latest_risk_snapshot.json  –  per-SKU risk assessment
  • data/raw/sales_data.csv              –  daily sales history
  • models/model_metrics.json           –  model benchmark results

Rendering rules (Windows Device Guard / DLL policy constraints):
  • NO pandas, NO pyarrow imports anywhere in this file
  • NO st.dataframe() / st.table() – use st.markdown(html) instead
  • Charts: st.vega_lite_chart() accepts plain list-of-dicts (no pandas needed)
  • Run with: python -m streamlit run src\\dashboard\\app.py
"""

import os
import csv
import json
import datetime
import collections
import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Inventory Intelligence Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# File path constants
# ---------------------------------------------------------------------------
BASE_DIR     = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT_PATH = os.path.join(BASE_DIR, "data",   "gold",   "latest_risk_snapshot.json")
METRICS_PATH  = os.path.join(BASE_DIR, "models", "model_metrics.json")
RAW_CSV_PATH  = os.path.join(BASE_DIR, "data",   "raw",    "sales_data.csv")

# ---------------------------------------------------------------------------
# Known dimension values (hard-coded once; derived from raw CSV)
# ---------------------------------------------------------------------------
ALL_STORES     = ["S001", "S002", "S003", "S004", "S005"]
ALL_PRODUCTS   = [f"P{i:04d}" for i in range(1, 21)]
ALL_CATEGORIES = ["Clothing", "Electronics", "Furniture", "Groceries", "Toys"]

# ---------------------------------------------------------------------------
# Badge / colour palettes
# ---------------------------------------------------------------------------
BADGE = {
    "HIGH_STOCKOUT_RISK":      "background:#ff4b4b;color:#fff;",
    "ELEVATED_STOCKOUT_RISK":  "background:#ffa421;color:#000;",
    "LOW_STOCKOUT_RISK":       "background:#21c354;color:#fff;",
    "CRITICAL_OVERSTOCK":      "background:#9d4edd;color:#fff;",
    "SLOW_MOVING":             "background:#ffaa00;color:#000;",
    "HEALTHY_VELOCITY":        "background:#21c354;color:#fff;",
    "EXPEDITE_ORDER":          "background:#d90429;color:#fff;",
    "MONITOR_REORDER":         "background:#f77f00;color:#000;",
    "PROMO_DISCOUNT":          "background:#7209b7;color:#fff;",
    "DELAY_PURCHASE":          "background:#e09f3e;color:#000;",
    "MAINTAIN_NORMAL":         "background:#2b9348;color:#fff;",
}

# ---------------------------------------------------------------------------
# Data loading helpers (all pure Python stdlib)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading risk snapshot…")
def load_snapshot():
    """Returns list of dicts from latest_risk_snapshot.json."""
    if not os.path.exists(SNAPSHOT_PATH):
        return None, f"Risk snapshot not found at `{SNAPSHOT_PATH}`.  " \
                     f"Run: `python src/risk/generate_risk_snapshot.py`"
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data, None


@st.cache_data(show_spinner="Loading model metrics…")
def load_metrics():
    """Returns metrics dict from model_metrics.json."""
    if not os.path.exists(METRICS_PATH):
        return None, f"Model metrics not found at `{METRICS_PATH}`.  " \
                     f"Run: `python src/forecasting/train_forecasting.py`"
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f), None


@st.cache_data(show_spinner="Loading sales history (this may take ~5 s)…")
def load_raw_history(store_id: str, product_id: str, days: int = 90):
    """
    Reads raw CSV (no pandas) and returns the last `days` rows for
    the given store+product as a list of dicts with keys:
      date (str), demand (float), inventory_level (float),
      units_sold (float), units_ordered (float), promotion (int)
    Sorted ascending by date.
    """
    if not os.path.exists(RAW_CSV_PATH):
        return None, f"Raw CSV not found at `{RAW_CSV_PATH}`."
    rows = []
    with open(RAW_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Store ID"] == store_id and row["Product ID"] == product_id:
                rows.append({
                    "date":            row["Date"],
                    "demand":          float(row["Demand"]),
                    "inventory_level": float(row["Inventory Level"]),
                    "units_sold":      float(row["Units Sold"]),
                    "units_ordered":   float(row["Units Ordered"]),
                    "promotion":       int(row["Promotion"]),
                    "category":        row["Category"],
                    "region":          row["Region"],
                })
    if not rows:
        return None, f"No records found for {store_id} / {product_id} in the raw CSV."
    rows.sort(key=lambda r: r["date"])
    return rows[-days:], None


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

def _badge(value: str) -> str:
    style = BADGE.get(value, "background:#555;color:#fff;")
    return (f'<span style="padding:2px 8px;border-radius:4px;'
            f'font-size:11px;font-weight:600;{style}">{value}</span>')


def _gap_cell(gap: float) -> str:
    colour = "#ff4b4b" if gap < 0 else "#21c354"
    sign   = "" if gap < 0 else "+"
    return (f'<td style="padding:8px 10px;text-align:right;'
            f'color:{colour};font-weight:bold;">{sign}{gap:.1f}</td>')


def _th(label: str, align: str = "left") -> str:
    return (f'<th style="padding:9px 10px;text-align:{align};'
            f'border-bottom:2px solid #444;white-space:nowrap;">{label}</th>')


def render_risk_table(rows: list, include_overstock_col: bool = False) -> str:
    """Pure-HTML table for the watchlist tabs.  Zero pandas usage."""
    if not rows:
        return "<p style='color:#888;padding:16px;'>No items match the current filters.</p>"

    ths = "".join([
        _th("Store"),
        _th("Product"),
        _th("Category"),
        _th("Region"),
        _th("Stock", "right"),
        _th("On Order", "right"),
        _th("7-Day Forecast", "right"),
        _th("Inventory Gap", "right"),
        _th("Cover (Days)", "right"),
        _th("Stockout Risk", "center"),
        *([ _th("Overstock Risk", "center")] if include_overstock_col else []),
        _th("Action", "center"),
        _th("Manager Guidance"),
    ])

    body = ""
    for i, r in enumerate(rows):
        bg = "#15181e" if i % 2 == 0 else "#0e1117"
        over_cell = (f'<td style="padding:8px 10px;text-align:center;">'
                     f'{_badge(r["overstock_risk"])}</td>'
                     if include_overstock_col else "")
        body += f"""
        <tr style="background:{bg};border-bottom:1px solid #262730;">
          <td style="padding:8px 10px;">{r['store_id']}</td>
          <td style="padding:8px 10px;font-weight:bold;">{r['product_id']}</td>
          <td style="padding:8px 10px;">{r['category']}</td>
          <td style="padding:8px 10px;">{r.get('region','—')}</td>
          <td style="padding:8px 10px;text-align:right;">{r['current_stock']:,}</td>
          <td style="padding:8px 10px;text-align:right;">{r['incoming_orders']:,}</td>
          <td style="padding:8px 10px;text-align:right;font-weight:bold;">{r['forecast_demand_7d']:.1f}</td>
          {_gap_cell(r['inventory_gap'])}
          <td style="padding:8px 10px;text-align:right;">{r['days_of_cover']:.1f}</td>
          <td style="padding:8px 10px;text-align:center;">{_badge(r['stockout_risk'])}</td>
          {over_cell}
          <td style="padding:8px 10px;text-align:center;">{_badge(r['status_action'])}</td>
          <td style="padding:8px 10px;font-size:12px;max-width:320px;">{r['recommendation']}</td>
        </tr>"""

    return f"""
    <div style="overflow-x:auto;max-height:560px;border-radius:8px;border:1px solid #333;">
      <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:13px;">
        <thead style="position:sticky;top:0;background:#1e222b;color:#f0f2f6;">
          <tr>{ths}</tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </div>"""


def render_metrics_table(comp: dict) -> str:
    """HTML benchmark comparison table for the Model Performance tab."""
    rows_html = ""
    order = [
        ("Baseline_Naive_Lag1",  "Naive Lag-1 × 7 (Baseline)"),
        ("Baseline_Rolling_7d",  "Rolling 7-Day Average (Baseline)"),
        ("Random_Forest_ML",     "🤖 Spark MLlib Random Forest"),
    ]
    best_mae  = min(v["MAE"]  for v in comp.values())
    best_wape = min(v["WAPE"] for v in comp.values())

    for key, label in order:
        if key not in comp:
            continue
        v     = comp[key]
        is_ml = key == "Random_Forest_ML"
        bg    = "#12261a" if is_ml else "#15181e"
        fw    = "font-weight:bold;" if is_ml else ""
        mae_s = "color:#21c354;font-weight:bold;" if v["MAE"] == best_mae else ""
        wpe_s = "color:#21c354;font-weight:bold;" if v["WAPE"] == best_wape else ""
        rows_html += f"""
        <tr style="background:{bg};border-bottom:1px solid #262730;">
          <td style="padding:9px 12px;{fw}">{label}</td>
          <td style="padding:9px 12px;text-align:right;{mae_s}">{v['MAE']}</td>
          <td style="padding:9px 12px;text-align:right;">{v['RMSE']}</td>
          <td style="padding:9px 12px;text-align:right;{wpe_s}">{v['WAPE']}%</td>
        </tr>"""

    return f"""
    <div style="border-radius:8px;border:1px solid #333;overflow:hidden;max-width:680px;">
      <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:14px;">
        <thead style="background:#1e222b;color:#f0f2f6;">
          <tr>
            {_th("Model / Baseline")} {_th("MAE","right")} {_th("RMSE","right")} {_th("WAPE","right")}
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""


def render_history_table(rows: list) -> str:
    """Compact history table for the Product Detail tab."""
    if not rows:
        return "<p style='color:#888;'>No history available.</p>"
    ths = "".join([
        _th("Date"), _th("Demand","right"), _th("Inventory","right"),
        _th("Units Sold","right"), _th("On Order","right"), _th("Promo","center"),
    ])
    body = ""
    for i, r in enumerate(rows[-30:]):   # show last 30 rows in table
        bg = "#15181e" if i % 2 == 0 else "#0e1117"
        promo = "✅" if r["promotion"] else "—"
        body += f"""
        <tr style="background:{bg};border-bottom:1px solid #262730;">
          <td style="padding:7px 10px;">{r['date']}</td>
          <td style="padding:7px 10px;text-align:right;">{int(r['demand'])}</td>
          <td style="padding:7px 10px;text-align:right;">{int(r['inventory_level'])}</td>
          <td style="padding:7px 10px;text-align:right;">{int(r['units_sold'])}</td>
          <td style="padding:7px 10px;text-align:right;">{int(r['units_ordered'])}</td>
          <td style="padding:7px 10px;text-align:center;">{promo}</td>
        </tr>"""
    return f"""
    <div style="overflow-x:auto;max-height:420px;border-radius:8px;border:1px solid #333;">
      <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:13px;">
        <thead style="position:sticky;top:0;background:#1e222b;color:#f0f2f6;">
          <tr>{ths}</tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </div>"""


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

st.title("📦 Inventory Intelligence Dashboard")
st.caption(
    "AI-powered demand forecasting and stock-risk management · "
    "Spark MLlib Random Forest · Snapshot: near real-time risk engine"
)

# --- Load data -------------------------------------------------------
snapshot, snap_err = load_snapshot()
metrics,  met_err  = load_metrics()

# --- Sidebar ---------------------------------------------------------
st.sidebar.header("🔍 Filters")

# Store / Product / Category selectors
sel_store    = st.sidebar.selectbox("Store",    ["ALL"] + ALL_STORES)
sel_category = st.sidebar.selectbox("Category", ["ALL"] + ALL_CATEGORIES)

# Product list can be filtered if snapshot is available
if snapshot:
    prod_in_snap = sorted({r["product_id"] for r in snapshot
                            if (sel_store == "ALL" or r["store_id"] == sel_store)
                            and (sel_category == "ALL" or r["category"] == sel_category)})
else:
    prod_in_snap = ALL_PRODUCTS
sel_product = st.sidebar.selectbox("Product", ["ALL"] + prod_in_snap)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Data sources**\n"
    "- Risk snapshot: `data/gold/latest_risk_snapshot.json`\n"
    "- History: `data/raw/sales_data.csv`\n"
    "- Model metrics: `models/model_metrics.json`"
)

# --- KPI strip -------------------------------------------------------
if snapshot:
    snap_date   = snapshot[0].get("snapshot_date", "unknown")
    monitored   = len(snapshot)
    high_so     = sum(1 for r in snapshot if r["stockout_risk"] == "HIGH_STOCKOUT_RISK")
    elevated_so = sum(1 for r in snapshot if r["stockout_risk"] == "ELEVATED_STOCKOUT_RISK")
    critical_ov = sum(1 for r in snapshot if r["overstock_risk"] == "CRITICAL_OVERSTOCK")
    slow_mv     = sum(1 for r in snapshot if r["overstock_risk"] == "SLOW_MOVING")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📦 Products Monitored",   monitored,
              f"{len({r['store_id'] for r in snapshot})} active stores")
    k2.metric("🚨 High Stockout Risk",   high_so,
              f"+{elevated_so} elevated", delta_color="inverse")
    k3.metric("📉 Overstock / Slow-Moving", critical_ov + slow_mv,
              f"{critical_ov} critical, {slow_mv} slow", delta_color="inverse")
    k4.metric("📅 Snapshot Date", snap_date)
else:
    st.warning(
        f"⚠️ Risk snapshot not available.\n\n"
        f"Expected at: `{SNAPSHOT_PATH}`\n\n"
        f"Run: `python src/risk/generate_risk_snapshot.py`"
    )

st.markdown("---")

# --- Filter helper ---------------------------------------------------
def apply_filters(rows):
    out = rows
    if sel_store    != "ALL": out = [r for r in out if r["store_id"]  == sel_store]
    if sel_category != "ALL": out = [r for r in out if r["category"]  == sel_category]
    if sel_product  != "ALL": out = [r for r in out if r["product_id"]== sel_product]
    return out

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
(tab_forecast, tab_stockout, tab_overstock,
 tab_detail,   tab_perf) = st.tabs([
    "📈 Demand Forecast View",
    "🚨 Stock-Out Watchlist",
    "📉 Overstock / Slow-Moving",
    "🔍 Product Detail",
    "📊 Model Performance",
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — DEMAND FORECAST VIEW
# Shows actual daily demand vs the model's 7-day forward forecast
# ═══════════════════════════════════════════════════════════════════════
with tab_forecast:
    st.subheader("Demand Forecast View")

    if sel_store == "ALL" or sel_product == "ALL":
        st.info(
            "Select a specific **Store** and **Product** in the sidebar "
            "to see the demand chart and forecast details."
        )
    else:
        hist, hist_err = load_raw_history(sel_store, sel_product, days=60)
        if hist_err:
            st.error(f"⚠️ Could not load history: {hist_err}")
        else:
            # Find matching snapshot record (the ML forecast)
            snap_rec = None
            if snapshot:
                for r in snapshot:
                    if r["store_id"] == sel_store and r["product_id"] == sel_product:
                        snap_rec = r
                        break

            # Info cards
            if snap_rec:
                fc1, fc2, fc3, fc4 = st.columns(4)
                fc1.metric("Current Stock",      f"{snap_rec['current_stock']:,} units")
                fc2.metric("Incoming Orders",    f"{snap_rec['incoming_orders']:,} units")
                fc3.metric("7-Day ML Forecast",  f"{snap_rec['forecast_demand_7d']:.1f} units")
                fc4.metric("Days of Cover",      f"{snap_rec['days_of_cover']:.1f} days")
                st.caption(
                    f"Store **{sel_store}** · Product **{sel_product}** · "
                    f"Category: **{snap_rec['category']}** · "
                    f"Region: **{snap_rec.get('region','—')}** · "
                    f"Snapshot date: `{snap_rec['snapshot_date']}`"
                )

            st.markdown("#### Last 60 Days – Actual Daily Demand")
            st.caption(
                "The **blue bars** show actual recorded demand (units/day) from the raw sales data. "
                "The **orange dashed line** shows the model's 7-day cumulative forecast "
                "(from the risk snapshot) as a daily-average reference line."
            )

            # Build vega-lite chart data (plain list of dicts — no pandas)
            chart_data = [
                {"date": r["date"], "Actual Demand": r["demand"]}
                for r in hist
            ]

            # Optional: overlay forecast daily average as a constant rule line
            forecast_daily_avg = None
            if snap_rec:
                forecast_daily_avg = round(snap_rec["forecast_demand_7d"] / 7, 2)

            vega_spec = {
                "width": "container",
                "height": 320,
                "layer": [
                    {
                        "mark": {"type": "bar", "color": "#4c9be8", "opacity": 0.85},
                        "encoding": {
                            "x": {"field": "date", "type": "temporal",
                                  "title": "Date",
                                  "axis": {"labelAngle": -35}},
                            "y": {"field": "Actual Demand", "type": "quantitative",
                                  "title": "Demand (units)"},
                            "tooltip": [
                                {"field": "date", "type": "temporal", "title": "Date"},
                                {"field": "Actual Demand", "type": "quantitative"},
                            ],
                        },
                    },
                ],
                "data": {"values": chart_data},
            }

            # Add forecast reference line if available
            if forecast_daily_avg is not None:
                vega_spec["layer"].append({
                    "mark": {
                        "type": "rule",
                        "color": "#ff7043",
                        "strokeWidth": 2,
                        "strokeDash": [6, 3],
                    },
                    "encoding": {
                        "y": {"datum": forecast_daily_avg,
                              "type": "quantitative"},
                        "tooltip": [
                            {"value": f"ML Forecast daily avg: {forecast_daily_avg} units"}
                        ],
                    },
                })
                st.caption(
                    f"🟠 Orange line = ML forecast daily average "
                    f"({snap_rec['forecast_demand_7d']:.1f} ÷ 7 = **{forecast_daily_avg} units/day**)"
                )

            st.vega_lite_chart(vega_spec, use_container_width=True)

            # Inventory level sub-chart
            st.markdown("#### Inventory Level Over Time")
            inv_data = [
                {"date": r["date"], "Inventory Level": r["inventory_level"]}
                for r in hist
            ]
            inv_spec = {
                "width": "container", "height": 200,
                "mark": {"type": "area", "color": "#5c8a8a", "opacity": 0.6,
                         "line": {"color": "#5c8a8a"}},
                "encoding": {
                    "x": {"field": "date", "type": "temporal",
                          "title": "Date", "axis": {"labelAngle": -35}},
                    "y": {"field": "Inventory Level", "type": "quantitative",
                          "title": "On-Hand Units"},
                    "tooltip": [
                        {"field": "date", "type": "temporal", "title": "Date"},
                        {"field": "Inventory Level", "type": "quantitative"},
                    ],
                },
                "data": {"values": inv_data},
            }
            st.vega_lite_chart(inv_spec, use_container_width=True)

            # Risk callout (if snapshot available)
            if snap_rec:
                st.markdown("#### Risk Assessment (from latest snapshot)")
                action_map = {
                    "EXPEDITE_ORDER":  ("🚨", "error",   "Urgent replenishment — expedite order immediately."),
                    "MONITOR_REORDER": ("⚠️", "warning", "Stock running low — raise purchase order soon."),
                    "PROMO_DISCOUNT":  ("📢", "warning", "Excess inventory — consider promotion or discount."),
                    "DELAY_PURCHASE":  ("⏸️", "info",    "Overstock detected — delay next purchase order."),
                    "MAINTAIN_NORMAL": ("✅", "success", "Inventory healthy — maintain normal ordering cadence."),
                }
                icon, level, default_msg = action_map.get(
                    snap_rec["status_action"], ("ℹ️", "info", "")
                )
                msg = f"{icon} **{snap_rec['status_action']}** · {snap_rec['recommendation']}"
                getattr(st, level)(msg)


# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — STOCK-OUT WATCHLIST
# ═══════════════════════════════════════════════════════════════════════
with tab_stockout:
    st.subheader("🚨 Stock-Out Watchlist")
    st.caption(
        "Products where forecast demand **exceeds available stock** within 7 days. "
        "Sorted by severity (HIGH first), then by days-of-cover ascending."
    )

    if snap_err:
        st.error(snap_err)
    elif snapshot:
        so_rows = [
            r for r in snapshot
            if r["stockout_risk"] in ("HIGH_STOCKOUT_RISK", "ELEVATED_STOCKOUT_RISK")
        ]
        so_rows = apply_filters(so_rows)
        so_rows.sort(
            key=lambda r: (
                0 if r["stockout_risk"] == "HIGH_STOCKOUT_RISK" else 1,
                r["days_of_cover"]
            )
        )

        high_n = sum(1 for r in so_rows if r["stockout_risk"] == "HIGH_STOCKOUT_RISK")
        elev_n = sum(1 for r in so_rows if r["stockout_risk"] == "ELEVATED_STOCKOUT_RISK")
        st.markdown(
            f"Showing **{len(so_rows)}** at-risk SKUs &nbsp;·&nbsp; "
            f"🔴 {high_n} HIGH &nbsp;·&nbsp; 🟡 {elev_n} ELEVATED"
        )
        st.markdown(render_risk_table(so_rows), unsafe_allow_html=True)

        st.caption(
            "**Inventory Gap** = (current stock + incoming orders) − 7-day forecast.  "
            "Negative = shortfall.  "
            "**Days of Cover** = current stock ÷ (forecast ÷ 7)."
        )
    else:
        st.info("No snapshot data loaded.")


# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — OVERSTOCK / SLOW-MOVING WATCHLIST
# ═══════════════════════════════════════════════════════════════════════
with tab_overstock:
    st.subheader("📉 Overstock & Slow-Moving Watchlist")
    st.caption(
        "Products where stock significantly **exceeds** 7-day forecast demand, "
        "indicating excess holding costs or weak sell-through."
    )

    if snap_err:
        st.error(snap_err)
    elif snapshot:
        ov_rows = [
            r for r in snapshot
            if r["overstock_risk"] in ("CRITICAL_OVERSTOCK", "SLOW_MOVING")
        ]
        ov_rows = apply_filters(ov_rows)
        ov_rows.sort(
            key=lambda r: (
                0 if r["overstock_risk"] == "CRITICAL_OVERSTOCK" else 1,
                -r["days_of_cover"]   # highest cover first
            )
        )

        crit_n = sum(1 for r in ov_rows if r["overstock_risk"] == "CRITICAL_OVERSTOCK")
        slow_n = sum(1 for r in ov_rows if r["overstock_risk"] == "SLOW_MOVING")
        st.markdown(
            f"Showing **{len(ov_rows)}** overstocked SKUs &nbsp;·&nbsp; "
            f"🟣 {crit_n} CRITICAL &nbsp;·&nbsp; 🟡 {slow_n} SLOW-MOVING"
        )
        st.markdown(
            render_risk_table(ov_rows, include_overstock_col=True),
            unsafe_allow_html=True,
        )

        st.caption(
            "**Days of Cover** > 21 = slow-moving. > 45 = critical overstock (rule thresholds).  "
            "Consider promotional pricing, order delays, or inter-store transfers."
        )
    else:
        st.info("No snapshot data loaded.")


# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — PRODUCT DETAIL VIEW
# ═══════════════════════════════════════════════════════════════════════
with tab_detail:
    st.subheader("🔍 Product Detail View")

    if sel_store == "ALL" or sel_product == "ALL":
        st.info(
            "Select a specific **Store** and **Product** in the sidebar "
            "to see the full 90-day history and risk breakdown."
        )
    else:
        hist90, hist90_err = load_raw_history(sel_store, sel_product, days=90)

        # --- Snapshot record (risk engine output) ---
        snap_rec = None
        if snapshot:
            for r in snapshot:
                if r["store_id"] == sel_store and r["product_id"] == sel_product:
                    snap_rec = r
                    break

        st.markdown(f"#### {sel_store} · {sel_product}")

        if snap_rec:
            # Summary cards
            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Category",       snap_rec["category"])
            d2.metric("Region",         snap_rec.get("region", "—"))
            d3.metric("Current Stock",  f"{snap_rec['current_stock']:,}")
            d4.metric("On Order",       f"{snap_rec['incoming_orders']:,}")
            d5.metric("Days of Cover",  f"{snap_rec['days_of_cover']:.1f}")

            # Risk row
            r1, r2, r3 = st.columns(3)
            r1.markdown(f"**Stockout Risk:** {_badge(snap_rec['stockout_risk'])}", unsafe_allow_html=True)
            r2.markdown(f"**Overstock Risk:** {_badge(snap_rec['overstock_risk'])}", unsafe_allow_html=True)
            r3.markdown(f"**Recommended Action:** {_badge(snap_rec['status_action'])}", unsafe_allow_html=True)

            st.info(f"📋 **Guidance:** {snap_rec['recommendation']}")
            st.caption(
                f"7-Day ML Forecast: **{snap_rec['forecast_demand_7d']:.1f} units** · "
                f"Inventory Gap: **{snap_rec['inventory_gap']:+.1f} units** · "
                f"Price: USD {snap_rec.get('price', 0):.2f} · "
                f"Snapshot: `{snap_rec['snapshot_date']}`"
            )
        else:
            st.warning(
                f"No snapshot record found for {sel_store}/{sel_product}. "
                f"Check that `generate_risk_snapshot.py` ran successfully."
            )

        st.markdown("---")
        st.markdown("#### 90-Day Demand & Inventory History")

        if hist90_err:
            st.error(f"⚠️ {hist90_err}")
        else:
            # Combined line chart: Demand + Inventory Level
            combo_data = []
            for r in hist90:
                combo_data.append({"date": r["date"], "metric": "Actual Demand",   "value": r["demand"]})
                combo_data.append({"date": r["date"], "metric": "Inventory Level",  "value": r["inventory_level"]})

            combo_spec = {
                "width": "container", "height": 300,
                "mark": "line",
                "encoding": {
                    "x": {"field": "date", "type": "temporal",
                          "title": "Date", "axis": {"labelAngle": -35}},
                    "y": {"field": "value", "type": "quantitative", "title": "Units"},
                    "color": {
                        "field": "metric", "type": "nominal",
                        "scale": {"range": ["#4c9be8", "#f4a261"]},
                    },
                    "tooltip": [
                        {"field": "date",   "type": "temporal",     "title": "Date"},
                        {"field": "metric", "type": "nominal",      "title": "Metric"},
                        {"field": "value",  "type": "quantitative", "title": "Value"},
                    ],
                },
                "data": {"values": combo_data},
            }
            st.vega_lite_chart(combo_spec, use_container_width=True)
            st.caption(
                "🔵 Blue = actual daily demand  ·  🟠 Orange = on-hand inventory level  "
                "(last 90 calendar days, from raw sales CSV)"
            )

            # Promotion activity
            promo_days = sum(1 for r in hist90 if r["promotion"])
            if promo_days:
                st.caption(f"📢 **Promotion active on {promo_days} of {len(hist90)} days** in this window.")

            st.markdown("#### Last 30 Days — Tabular History")
            st.caption("Scroll table to see all columns.  Shows the 30 most recent records.")
            st.markdown(render_history_table(hist90), unsafe_allow_html=True)

        # --- Demand rate summary ---
        if hist90 and not hist90_err:
            demands = [r["demand"] for r in hist90]
            avg_d   = sum(demands) / len(demands)
            max_d   = max(demands)
            min_d   = min(demands)
            st.markdown("#### Demand Statistics (Last 90 Days)")
            s1, s2, s3 = st.columns(3)
            s1.metric("Average Daily Demand", f"{avg_d:.1f} units")
            s2.metric("Peak Daily Demand",    f"{max_d:.0f} units")
            s3.metric("Minimum Daily Demand", f"{min_d:.0f} units")


# ═══════════════════════════════════════════════════════════════════════
# TAB 5 — MODEL PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════
with tab_perf:
    st.subheader("📊 Forecasting Model Performance")

    if met_err:
        st.error(met_err)
    elif metrics:
        splits = metrics.get("chronological_splits", {})
        tp     = metrics.get("test_performance", {})
        comp   = metrics.get("validation_comparison", {})
        feat   = metrics.get("features", [])

        # Model spec
        st.markdown(
            f"**Model:** `{metrics.get('model_type')}` · "
            f"**{metrics.get('trees')} trees** · "
            f"**Max depth {metrics.get('max_depth')}** · "
            f"**Target:** `{metrics.get('target')}`"
        )

        st.markdown("#### Chronological Train / Val / Test Split")
        sc1, sc2, sc3 = st.columns(3)
        sc1.info(f"**Training**\n\n{splits.get('train_period','—')}\n\n~50,300 rows")
        sc2.info(f"**Validation**\n\n{splits.get('val_period','—')}\n\n~12,200 rows")
        sc3.info(f"**Held-out Test**\n\n{splits.get('test_period','—')}\n\n~10,000 rows")

        st.markdown("---")
        st.markdown("#### Benchmark Comparison (Validation Set)")
        st.markdown(render_metrics_table(comp), unsafe_allow_html=True)
        st.caption(
            "**MAE** = Mean Absolute Error (units) · **RMSE** = Root Mean Squared Error · "
            "**WAPE** = Weighted Absolute Percentage Error (lower is better).  "
            "🟢 Green = best result in each metric."
        )

        st.markdown("---")
        st.markdown("#### Hold-out Test Performance (unseen data)")
        t1, t2, t3 = st.columns(3)
        t1.metric("Test MAE",  f"{tp.get('MAE','—')} units")
        t2.metric("Test RMSE", f"{tp.get('RMSE','—')} units")
        t3.metric("Test WAPE", f"{tp.get('WAPE','—')}%")
        st.caption(
            "Test period is strictly after the validation period — the model was never "
            "trained or tuned on these dates, ensuring a realistic out-of-sample estimate."
        )

        # Feature list
        st.markdown("---")
        st.markdown("#### Features Used by the Model")
        cols = st.columns(3)
        for idx, feat_name in enumerate(feat):
            cols[idx % 3].markdown(f"- `{feat_name}`")

        # Improvement summary
        if "Baseline_Naive_Lag1" in comp and "Random_Forest_ML" in comp:
            naive_wape = comp["Baseline_Naive_Lag1"]["WAPE"]
            ml_wape    = comp["Random_Forest_ML"]["WAPE"]
            lift_pct   = round((naive_wape - ml_wape) / naive_wape * 100, 1)
            st.success(
                f"✅ The ML model reduced WAPE by **{lift_pct}%** vs the naive lag baseline "
                f"({naive_wape}% → {ml_wape}%) on the validation set."
            )
    else:
        st.info("No model metrics available yet.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "Inventory Intelligence Dashboard · "
    "Spark MLlib Random Forest · "
    "Data as of snapshot date shown above · "
    "No pandas / pyarrow dependencies (Windows Device Guard–safe)"
)
