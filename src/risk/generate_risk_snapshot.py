"""
Phase 5: Forecast and Stock Risk Batch Scorer
Generates forward-looking predictions and inventory risk assessments
for the latest observed date, persisting results as JSON for the API and Dashboard.
"""

import sys
import os
import json
from pyspark.ml import PipelineModel
from pyspark.sql import functions as F

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.common.spark_utils import get_spark_session
from src.risk.risk_engine import evaluate_inventory_risk

def generate_risk_recommendations(spark, gold_path: str, model_path: str, output_path: str):
    print(f"Loading Gold data from {gold_path} and model from {model_path}...")
    gold = spark.read.parquet(gold_path)
    latest_date = gold.select(F.max("date")).first()[0]
    print(f"Latest observed date in data: {latest_date}")

    latest_snapshot = gold.filter(F.col("date") == latest_date)
    model = PipelineModel.load(model_path)
    predictions = model.transform(latest_snapshot)

    rows = predictions.select(
        "date", "store_id", "product_id", "category", "region",
        "inventory_level", "units_ordered", "price", "prediction"
    ).collect()

    evaluations = []
    for r in rows:
        assessment = evaluate_inventory_risk(
            store_id=r["store_id"],
            product_id=r["product_id"],
            category=r["category"],
            current_stock=r["inventory_level"],
            units_ordered=r["units_ordered"],
            forecast_7d=r["prediction"]
        )
        assessment["region"] = r["region"]
        assessment["price"] = round(r["price"], 2)
        assessment["snapshot_date"] = str(r["date"])
        evaluations.append(assessment)

    print(f"Generated {len(evaluations)} risk evaluations.")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(evaluations, f, indent=2)

    print(f"Saved risk evaluation snapshot to {output_path}")
    return evaluations

if __name__ == "__main__":
    spark = get_spark_session("risk-batch-scorer")
    try:
        generate_risk_recommendations(
            spark,
            "data/gold/sales_gold",
            "models/rf_demand_model",
            "data/gold/latest_risk_snapshot.json"
        )
    finally:
        spark.stop()
