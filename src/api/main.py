"""
FastAPI Serving Backend
Exposes prediction, stock-risk evaluation, and model metadata endpoints:
- GET  /health: Service status & loaded model version
- GET  /metrics: Validation and test evaluation metrics
- GET  /risks: Query inventory risk snapshot (filters for store, category, risk level)
- POST /predict-demand-risk: Real-time demand forecast & inventory risk evaluation
"""

import os
import json
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(
    title="AI Inventory Demand & Stock Risk Prediction Service",
    description="Production-grade API connecting demand forecasting to actionable inventory decisions.",
    version="1.0.0"
)

# Load cached model metrics and latest risk snapshot
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
METRICS_PATH = os.path.join(BASE_DIR, "models", "model_metrics.json")
RISK_SNAPSHOT_PATH = os.path.join(BASE_DIR, "data", "gold", "latest_risk_snapshot.json")

def load_json_file(path: str):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None

class PredictionRequest(BaseModel):
    store_id: str = Field(..., example="S001")
    product_id: str = Field(..., example="P0004")
    category: Optional[str] = Field("Electronics", example="Electronics")
    inventory_level: int = Field(..., ge=0, example=80)
    units_ordered: int = Field(0, ge=0, example=20)
    forecast_horizon_days: int = Field(7, example=7)
    recent_daily_demand_avg: float = Field(..., gt=0, example=17.5)

class PredictionResponse(BaseModel):
    store_id: str
    product_id: str
    category: str
    forecast_horizon_days: int
    predicted_demand: float
    current_inventory: int
    incoming_orders: int
    inventory_gap: float
    days_of_cover: float
    stockout_risk: str
    overstock_risk: str
    status_action: str
    recommendation: str

@app.get("/health")
def health():
    metrics = load_json_file(METRICS_PATH)
    return {
        "status": "healthy",
        "service": "inventory-demand-risk-engine",
        "model_version": metrics.get("model_type", "RandomForest_SparkML") if metrics else "initialized",
        "latest_snapshot_available": os.path.exists(RISK_SNAPSHOT_PATH)
    }

@app.get("/metrics")
def get_model_metrics():
    metrics = load_json_file(METRICS_PATH)
    if not metrics:
        raise HTTPException(status_code=404, detail="Model metrics file not found.")
    return metrics

@app.get("/risks")
def get_inventory_risks(
    store_id: Optional[str] = None,
    category: Optional[str] = None,
    stockout_risk: Optional[str] = None,
    overstock_risk: Optional[str] = None,
    limit: int = Query(50, le=100)
):
    snapshot = load_json_file(RISK_SNAPSHOT_PATH)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Latest risk snapshot not found. Run batch scorer first.")
    
    filtered = snapshot
    if store_id:
        filtered = [r for r in filtered if r.get("store_id") == store_id]
    if category:
        filtered = [r for r in filtered if r.get("category", "").lower() == category.lower()]
    if stockout_risk:
        filtered = [r for r in filtered if r.get("stockout_risk") == stockout_risk]
    if overstock_risk:
        filtered = [r for r in filtered if r.get("overstock_risk") == overstock_risk]

    return {
        "total_matches": len(filtered),
        "snapshot_date": snapshot[0].get("snapshot_date") if snapshot else None,
        "results": filtered[:limit]
    }

@app.post("/predict-demand-risk", response_model=PredictionResponse)
def predict_demand_and_risk(req: PredictionRequest):
    # Rule/Model powered real-time forecast estimation
    forecast_demand_7d = round(req.recent_daily_demand_avg * req.forecast_horizon_days, 1)
    effective_stock = req.inventory_level + req.units_ordered
    gap = effective_stock - forecast_demand_7d
    days_of_cover = round(req.inventory_level / max(forecast_demand_7d / req.forecast_horizon_days, 0.1), 1)

    if effective_stock < forecast_demand_7d:
        stockout_risk = "HIGH_STOCKOUT_RISK"
        shortfall = int(forecast_demand_7d - effective_stock)
        recommendation = f"Urgent replenishment needed! Shortfall of {shortfall} units projected."
        status_action = "EXPEDITE_ORDER"
    elif effective_stock < forecast_demand_7d * 1.15:
        stockout_risk = "ELEVATED_STOCKOUT_RISK"
        recommendation = f"Stock level tight ({days_of_cover} days cover). Monitor reorder window."
        status_action = "MONITOR_REORDER"
    else:
        stockout_risk = "LOW_STOCKOUT_RISK"
        status_action = "MAINTAIN_NORMAL"
        recommendation = f"Healthy inventory buffer ({days_of_cover} days cover)."

    if days_of_cover > 45.0:
        overstock_risk = "CRITICAL_OVERSTOCK"
        recommendation = f"High holding risk ({days_of_cover} days cover). Review promotional discount."
        status_action = "PROMO_DISCOUNT"
    elif days_of_cover > 25.0:
        overstock_risk = "SLOW_MOVING"
    else:
        overstock_risk = "HEALTHY_VELOCITY"

    return PredictionResponse(
        store_id=req.store_id,
        product_id=req.product_id,
        category=req.category,
        forecast_horizon_days=req.forecast_horizon_days,
        predicted_demand=forecast_demand_7d,
        current_inventory=req.inventory_level,
        incoming_orders=req.units_ordered,
        inventory_gap=round(gap, 1),
        days_of_cover=days_of_cover,
        stockout_risk=stockout_risk,
        overstock_risk=overstock_risk,
        status_action=status_action,
        recommendation=recommendation
    )
