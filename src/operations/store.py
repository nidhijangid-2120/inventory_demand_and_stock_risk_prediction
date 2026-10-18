"""Small local operations store for sales, on-hand stock, and purchase orders."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import defaultdict
from datetime import date


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "operations.sqlite3")
SNAPSHOT_PATH = os.path.join(BASE_DIR, "data", "gold", "latest_risk_snapshot.json")
SALES_CSV_PATH = os.path.join(BASE_DIR, "data", "raw", "sales_data.csv")
ACTIVE_RUN_PATH = os.path.join(BASE_DIR, "data", "processed", "active_retraining_run.json")


def active_sources():
    if os.path.exists(ACTIVE_RUN_PATH):
        try:
            with open(ACTIVE_RUN_PATH, encoding="utf-8") as f:
                active = json.load(f)
            return (
                os.path.join(BASE_DIR, active["snapshot_path"].replace("/", os.sep)),
                os.path.join(BASE_DIR, active["sales_path"].replace("/", os.sep)),
            )
        except (OSError, KeyError, json.JSONDecodeError):
            pass
    return SNAPSHOT_PATH, SALES_CSV_PATH


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    snapshot_path, sales_csv_path = active_sources()
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS inventory (store_id TEXT NOT NULL, product_id TEXT NOT NULL, category TEXT, current_stock INTEGER NOT NULL, incoming_orders INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (store_id, product_id))")
        db.execute("CREATE TABLE IF NOT EXISTS daily_sales (sale_date TEXT NOT NULL, store_id TEXT NOT NULL, product_id TEXT NOT NULL, units_sold INTEGER NOT NULL, PRIMARY KEY (sale_date, store_id, product_id))")
        db.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, kind TEXT NOT NULL, store_id TEXT NOT NULL, product_id TEXT NOT NULL, quantity INTEGER NOT NULL)")

        if db.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0 and os.path.exists(snapshot_path):
            with open(snapshot_path, encoding="utf-8") as f:
                snapshot = json.load(f)
            db.executemany(
                "INSERT OR IGNORE INTO inventory VALUES (?, ?, ?, ?, ?)",
                [(r["store_id"], r["product_id"], r.get("category", "General"), int(r.get("current_stock", 0)), int(r.get("incoming_orders", 0))) for r in snapshot],
            )

        if db.execute("SELECT COUNT(*) FROM daily_sales").fetchone()[0] == 0 and os.path.exists(sales_csv_path):
            totals = defaultdict(int)
            with open(sales_csv_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        key = (date.fromisoformat(row["Date"].strip()).isoformat(), row["Store ID"].strip(), row["Product ID"].strip())
                        totals[key] += max(0, int(row["Units Sold"]))
                    except (KeyError, ValueError, AttributeError):
                        continue
            db.executemany("INSERT OR IGNORE INTO daily_sales VALUES (?, ?, ?, ?)", [(d, s, p, units) for (d, s, p), units in totals.items()])


def inventory_rows():
    initialize()
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM inventory ORDER BY store_id, product_id")]


def refresh_from_sources(snapshot_path: str, sales_csv_path: str):
    """Rebase inventory and daily demand after a complete CSV retraining run."""
    initialize()
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    totals = defaultdict(int)
    with open(sales_csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                key = (date.fromisoformat(row["Date"].strip()).isoformat(), row["Store ID"].strip(), row["Product ID"].strip())
                totals[key] += max(0, int(row["Units Sold"]))
            except (KeyError, ValueError, AttributeError):
                continue
    with connect() as db:
        db.execute("DELETE FROM inventory")
        db.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?) ON CONFLICT(store_id, product_id) DO UPDATE SET category=excluded.category, current_stock=excluded.current_stock, incoming_orders=excluded.incoming_orders",
            [(r["store_id"], r["product_id"], r.get("category", "General"), int(r.get("current_stock", 0)), int(r.get("incoming_orders", 0))) for r in snapshot],
        )
        db.execute("DELETE FROM daily_sales")
        db.executemany("INSERT INTO daily_sales VALUES (?, ?, ?, ?)", [(d, s, p, units) for (d, s, p), units in totals.items()])


def record_sale(store_id: str, product_id: str, units: int, sale_date: date):
    initialize()
    with connect() as db:
        row = db.execute("SELECT current_stock FROM inventory WHERE store_id=? AND product_id=?", (store_id, product_id)).fetchone()
        if row is None:
            raise KeyError(f"Unknown store/product {store_id}/{product_id}; add it to the inventory snapshot first.")
        db.execute("UPDATE inventory SET current_stock=MAX(0, current_stock-?) WHERE store_id=? AND product_id=?", (units, store_id, product_id))
        db.execute("INSERT INTO daily_sales VALUES (?, ?, ?, ?) ON CONFLICT(sale_date, store_id, product_id) DO UPDATE SET units_sold=units_sold+excluded.units_sold", (sale_date.isoformat(), store_id, product_id, units))
        db.execute("INSERT INTO transactions(kind, store_id, product_id, quantity) VALUES ('sale', ?, ?, ?)", (store_id, product_id, units))
        current = db.execute("SELECT * FROM inventory WHERE store_id=? AND product_id=?", (store_id, product_id)).fetchone()
        return dict(current)


def place_order(store_id: str, product_id: str, units: int):
    initialize()
    with connect() as db:
        cursor = db.execute("UPDATE inventory SET incoming_orders=incoming_orders+? WHERE store_id=? AND product_id=?", (units, store_id, product_id))
        if cursor.rowcount == 0:
            raise KeyError(f"Unknown store/product {store_id}/{product_id}; add it to the inventory snapshot first.")
        db.execute("INSERT INTO transactions(kind, store_id, product_id, quantity) VALUES ('purchase_order', ?, ?, ?)", (store_id, product_id, units))
        return dict(db.execute("SELECT * FROM inventory WHERE store_id=? AND product_id=?", (store_id, product_id)).fetchone())


def receive_order(store_id: str, product_id: str, units: int):
    initialize()
    with connect() as db:
        row = db.execute("SELECT incoming_orders FROM inventory WHERE store_id=? AND product_id=?", (store_id, product_id)).fetchone()
        if row is None:
            raise KeyError(f"Unknown store/product {store_id}/{product_id}; add it to the inventory snapshot first.")
        if units > row["incoming_orders"]:
            raise ValueError("Received quantity cannot exceed the units currently on order.")
        db.execute("UPDATE inventory SET incoming_orders=incoming_orders-?, current_stock=current_stock+? WHERE store_id=? AND product_id=?", (units, units, store_id, product_id))
        db.execute("INSERT INTO transactions(kind, store_id, product_id, quantity) VALUES ('receipt', ?, ?, ?)", (store_id, product_id, units))
        return dict(db.execute("SELECT * FROM inventory WHERE store_id=? AND product_id=?", (store_id, product_id)).fetchone())


def update_stock(store_id: str, product_id: str, category: str, current_stock: int):
    initialize()
    with connect() as db:
        db.execute("INSERT INTO inventory VALUES (?, ?, ?, ?, 0) ON CONFLICT(store_id, product_id) DO UPDATE SET category=excluded.category, current_stock=excluded.current_stock", (store_id, product_id, category, current_stock))
        db.execute("INSERT INTO transactions(kind, store_id, product_id, quantity) VALUES ('stock_adjustment', ?, ?, ?)", (store_id, product_id, current_stock))
        return dict(db.execute("SELECT * FROM inventory WHERE store_id=? AND product_id=?", (store_id, product_id)).fetchone())


def risk_rows():
    initialize()
    snapshot_path, _ = active_sources()
    if not os.path.exists(snapshot_path):
        return []
    with open(snapshot_path, encoding="utf-8") as f:
        baseline = json.load(f)
    with connect() as db:
        rows = db.execute("SELECT sale_date, store_id, product_id, units_sold FROM daily_sales ORDER BY store_id, product_id, sale_date DESC").fetchall()
        recent_daily = defaultdict(list)
        for row in rows:
            key = (row["store_id"], row["product_id"])
            if len(recent_daily[key]) < 28:
                recent_daily[key].append(int(row["units_sold"]))
        inventory = {(r["store_id"], r["product_id"]): dict(r) for r in db.execute("SELECT * FROM inventory")}
    results = []
    for source in baseline:
        key = (source["store_id"], source["product_id"])
        current = inventory.get(key)
        if current is None:
            continue
        # The saved ML forecast is the cold-start fallback. Once recent daily
        # history exists, use that observed 28-day rate for the live projection.
        forecast = round(sum(recent_daily[key]) / len(recent_daily[key]) * 7, 1) if key in recent_daily else float(source.get("forecast_demand_7d", 0))
        available = current["current_stock"] + current["incoming_orders"]
        if available < forecast:
            stockout, severity = "HIGH_STOCKOUT_RISK", 3
        elif available < forecast * 1.15:
            stockout, severity = "ELEVATED_STOCKOUT_RISK", 2
        else:
            stockout, severity = "LOW_STOCKOUT_RISK", 1
        cover = round(current["current_stock"] / max(forecast / 7, 0.1), 1)
        overstock = "CRITICAL_OVERSTOCK" if cover > 45 else "SLOW_MOVING" if cover > 25 else "HEALTHY_VELOCITY"
        if severity == 3:
            action, recommendation = "EXPEDITE_ORDER", f"Urgent replenishment needed. Estimated 7-day demand exceeds available stock by {max(0, round(forecast-available))} units."
        elif severity == 2:
            action, recommendation = "MONITOR_REORDER", "Stock is close to the 7-day demand buffer; monitor replenishment."
        elif overstock == "CRITICAL_OVERSTOCK":
            action, recommendation = "PROMO_DISCOUNT", "High days of cover; review a purchase pause or promotion."
        elif overstock == "SLOW_MOVING":
            action, recommendation = "DELAY_PURCHASE", "Inventory cover is high; consider delaying the next purchase."
        else:
            action, recommendation = "MAINTAIN_NORMAL", "Current stock covers estimated demand."
        results.append({**source, **current, "forecast_demand_7d": forecast, "inventory_gap": round(available-forecast, 1), "days_of_cover": cover, "stockout_risk": stockout, "overstock_risk": overstock, "status_action": action, "recommendation": recommendation, "forecast_source": "latest 28 recorded sales days" if key in recent_daily else "saved ML forecast", "snapshot_date": date.today().isoformat()})
    return results
