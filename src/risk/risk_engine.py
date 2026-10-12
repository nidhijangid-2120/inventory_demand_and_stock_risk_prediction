"""
Phase 4: Inventory Risk Engine
Applies rule-based risk policies and business formulas to combine:
1. Forecast Demand (7-day ahead from model)
2. Current Available Inventory
3. Units on Order (pending replenishment)
4. Lead Time / Safety Stock assumptions

Calculates:
- Inventory Gap = Current Stock + Incoming Orders - Forecast Demand
- Days of Cover = (Current Stock / (Forecast Demand / 7))
- Stock-out Risk Score & Flag: 'High Stock-out Risk', 'Elevated Risk', 'Balanced'
- Slow-moving / Overstock Risk: 'Critical Overstock', 'Slow-Moving', 'Healthy'
- Business Recommendation: Actionable guidance for store and inventory managers
"""

from typing import Dict, Any, List

def evaluate_inventory_risk(
    store_id: str,
    product_id: str,
    category: str,
    current_stock: int,
    units_ordered: int,
    forecast_7d: float,
    safety_stock_buffer_pct: float = 0.15
) -> Dict[str, Any]:
    """
    Evaluates stock-out and overstock risk for a single store-product pair.
    """
    daily_forecast = max(forecast_7d / 7.0, 0.1)  # avoid division by zero
    effective_stock = current_stock + units_ordered
    inventory_gap = effective_stock - forecast_7d
    
    # Days of cover based on forward-looking daily forecast rate
    days_of_cover = round(current_stock / daily_forecast, 1)

    # 1. Stock-out Risk Analysis
    if effective_stock < forecast_7d:
        stockout_risk = "HIGH_STOCKOUT_RISK"
        stockout_severity = 3
    elif effective_stock < forecast_7d * (1.0 + safety_stock_buffer_pct):
        stockout_risk = "ELEVATED_STOCKOUT_RISK"
        stockout_severity = 2
    else:
        stockout_risk = "LOW_STOCKOUT_RISK"
        stockout_severity = 1

    # 2. Overstock / Slow-Moving Analysis
    # If days of cover exceeds 30-45 days while sales velocity is low
    if days_of_cover > 45.0:
        overstock_risk = "CRITICAL_OVERSTOCK"
    elif days_of_cover > 25.0:
        overstock_risk = "SLOW_MOVING"
    else:
        overstock_risk = "HEALTHY_VELOCITY"

    # 3. Formulate Actionable Manager Recommendations
    if stockout_severity == 3:
        shortfall = int(forecast_7d - effective_stock)
        recommendation = f"Urgent replenishment needed! Deficit of ~{shortfall} units projected over next 7 days."
        status_action = "EXPEDITE_ORDER"
    elif stockout_severity == 2:
        recommendation = f"Stock is tight ({days_of_cover} days cover). Monitor closely and schedule standard replenishment."
        status_action = "MONITOR_REORDER"
    elif overstock_risk == "CRITICAL_OVERSTOCK":
        excess = int(current_stock - (forecast_7d * 2))
        recommendation = f"High holding risk ({days_of_cover} days cover). Pause reordering; evaluate promotional discount or bundle."
        status_action = "PROMO_DISCOUNT"
    elif overstock_risk == "SLOW_MOVING":
        recommendation = f"Moderate excess buffer ({days_of_cover} days cover). Delay upcoming purchasing batch."
        status_action = "DELAY_PURCHASE"
    else:
        recommendation = f"Stock levels optimal ({days_of_cover} days cover). Maintain regular replenishment cycle."
        status_action = "MAINTAIN_NORMAL"

    return {
        "store_id": store_id,
        "product_id": product_id,
        "category": category,
        "current_stock": current_stock,
        "incoming_orders": units_ordered,
        "forecast_demand_7d": round(forecast_7d, 1),
        "inventory_gap": round(inventory_gap, 1),
        "days_of_cover": days_of_cover,
        "stockout_risk": stockout_risk,
        "overstock_risk": overstock_risk,
        "status_action": status_action,
        "recommendation": recommendation
    }

def batch_evaluate_risk(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluates inventory risk across a list of product-store records."""
    return [
        evaluate_inventory_risk(
            store_id=r["store_id"],
            product_id=r["product_id"],
            category=r.get("category", "General"),
            current_stock=r["inventory_level"],
            units_ordered=r.get("units_ordered", 0),
            forecast_7d=r["forecast_demand_7d"]
        )
        for r in records
    ]

if __name__ == "__main__":
    # Test cases matching the project guidelines
    cases = [
        {"store_id": "S001", "product_id": "P0001", "category": "Electronics", "inventory_level": 80, "units_ordered": 0, "forecast_demand_7d": 120.0},
        {"store_id": "S001", "product_id": "P0002", "category": "Clothing", "inventory_level": 250, "units_ordered": 0, "forecast_demand_7d": 35.0},
        {"store_id": "S002", "product_id": "P0003", "category": "Groceries", "inventory_level": 90, "units_ordered": 20, "forecast_demand_7d": 70.0}
    ]
    results = batch_evaluate_risk(cases)
    for res in results:
        print(f"[{res['store_id']} | {res['product_id']}] Gap: {res['inventory_gap']} | Cover: {res['days_of_cover']}d | Action: {res['status_action']}")
        print(f" -> Rec: {res['recommendation']}\n")
