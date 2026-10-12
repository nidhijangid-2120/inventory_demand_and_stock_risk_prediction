"""
Phase 3: Chronological Baselines and Spark MLlib Demand Forecasting Pipeline
Implements:
1. Baselines:
   - Naive Recent Demand Baseline (lag_1 * 7)
   - Rolling Average Baseline (rolling_demand_mean_7 * 7)
2. Machine Learning:
   - Feature Vectorization (VectorAssembler) & StringIndexer for categorical features
   - Random Forest Regressor & Gradient-Boosted Trees (GBTRegressor)
3. Model Evaluation:
   - MAE (Mean Absolute Error)
   - RMSE (Root Mean Squared Error)
   - WAPE (Weighted Absolute Percentage Error: sum(|y - y_hat|) / sum(y) * 100)
4. Model Persistence:
   - Saves best pipeline model and performance metadata to disk.
"""

import sys
import os
import json
from pyspark.sql import functions as F
from pyspark.ml import Pipeline
from pyspark.ml.feature import StringIndexer, VectorAssembler
from pyspark.ml.regression import RandomForestRegressor, GBTRegressor
from pyspark.ml.evaluation import RegressionEvaluator

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.common.spark_utils import get_spark_session

def calculate_wape(df, label_col="target_demand_next_7d", pred_col="prediction"):
    metrics = df.select(
        F.sum(F.abs(F.col(label_col) - F.col(pred_col))).alias("sum_abs_err"),
        F.sum(F.col(label_col)).alias("sum_actual")
    ).first()
    if metrics["sum_actual"] and metrics["sum_actual"] > 0:
        return (metrics["sum_abs_err"] / metrics["sum_actual"]) * 100.0
    return 0.0

def train_and_evaluate(spark, gold_path: str, model_output_path: str):
    print(f"--- [Phase 3] Loading Gold Dataset from {gold_path} ---")
    df = spark.read.parquet(gold_path)

    # 1. Chronological Split (Strictly Time-Based)
    train_end = "2023-06-15"
    val_end = "2023-10-15"

    train_df = df.filter(F.col("date") <= train_end).cache()
    val_df = df.filter((F.col("date") > train_end) & (F.col("date") <= val_end)).cache()
    test_df = df.filter(F.col("date") > val_end).cache()

    print(f"Dataset split counts -> Train: {train_df.count()} | Val: {val_df.count()} | Test: {test_df.count()}")

    target_col = "target_demand_next_7d"

    # --- 2. Evaluate Simple Baselines on Validation Set ---
    # Baseline 1: Recent Day Lag 1 scaled to 7 days
    val_b1 = val_df.withColumn("prediction", F.col("demand_lag_1") * 7.0)
    mae_eval = RegressionEvaluator(labelCol=target_col, predictionCol="prediction", metricName="mae")
    rmse_eval = RegressionEvaluator(labelCol=target_col, predictionCol="prediction", metricName="rmse")

    b1_mae = mae_eval.evaluate(val_b1)
    b1_rmse = rmse_eval.evaluate(val_b1)
    b1_wape = calculate_wape(val_b1, target_col, "prediction")
    print(f"\n[Baseline 1 - Naive Lag1 x 7] Validation -> MAE: {b1_mae:.2f}, RMSE: {b1_rmse:.2f}, WAPE: {b1_wape:.2f}%")

    # Baseline 2: 7-day Historical Rolling Average scaled to 7 days
    val_b2 = val_df.withColumn("prediction", F.col("rolling_demand_mean_7") * 7.0)
    b2_mae = mae_eval.evaluate(val_b2)
    b2_rmse = rmse_eval.evaluate(val_b2)
    b2_wape = calculate_wape(val_b2, target_col, "prediction")
    print(f"[Baseline 2 - Rolling 7d Avg x 7] Validation -> MAE: {b2_mae:.2f}, RMSE: {b2_rmse:.2f}, WAPE: {b2_wape:.2f}%")

    # --- 3. Build Spark ML Pipeline ---
    categorical_cols = ["store_id", "product_id", "category", "region", "weather_condition", "seasonality"]
    indexers = [
        StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep")
        for c in categorical_cols
    ]

    numeric_features = [
        "inventory_level", "price", "discount", "promotion", "competitor_pricing", "epidemic",
        "day_of_week", "day_of_month", "month", "is_weekend",
        "demand_lag_1", "demand_lag_7", "demand_lag_14", "demand_lag_28",
        "rolling_demand_mean_7", "rolling_demand_mean_14", "rolling_demand_mean_28",
        "price_to_comp_ratio", "is_discounted"
    ]
    indexed_cat_cols = [f"{c}_idx" for c in categorical_cols]
    all_feature_cols = numeric_features + indexed_cat_cols

    assembler = VectorAssembler(inputCols=all_feature_cols, outputCol="features", handleInvalid="keep")

    # Random Forest Regressor
    rf = RandomForestRegressor(
        featuresCol="features",
        labelCol=target_col,
        predictionCol="prediction",
        numTrees=40,
        maxDepth=8,
        seed=42
    )

    pipeline_rf = Pipeline(stages=indexers + [assembler, rf])

    print("\n--- Training Spark ML Random Forest Regressor ---")
    model_rf = pipeline_rf.fit(train_df)

    # Evaluate on Validation Set
    val_preds = model_rf.transform(val_df).cache()
    rf_mae = mae_eval.evaluate(val_preds)
    rf_rmse = rmse_eval.evaluate(val_preds)
    rf_wape = calculate_wape(val_preds, target_col, "prediction")
    print(f"[Random Forest ML] Validation -> MAE: {rf_mae:.2f}, RMSE: {rf_rmse:.2f}, WAPE: {rf_wape:.2f}%")

    # Evaluate on Unseen Future Test Set
    test_preds = model_rf.transform(test_df).cache()
    test_mae = mae_eval.evaluate(test_preds)
    test_rmse = rmse_eval.evaluate(test_preds)
    test_wape = calculate_wape(test_preds, target_col, "prediction")
    print(f"\n[Random Forest ML] HELD-OUT TEST (Unseen Future) -> MAE: {test_mae:.2f}, RMSE: {test_rmse:.2f}, WAPE: {test_wape:.2f}%")

    # --- 4. Persist Model and Performance Artifacts ---
    print(f"\nSaving fitted model to {model_output_path}...")
    model_rf.write().overwrite().save(model_output_path)

    metrics_summary = {
        "model_type": "Spark_MLlib_RandomForestRegressor",
        "trees": 40,
        "max_depth": 8,
        "features": all_feature_cols,
        "target": target_col,
        "chronological_splits": {
            "train_period": f"<= {train_end}",
            "val_period": f"{train_end} to {val_end}",
            "test_period": f"> {val_end}"
        },
        "validation_comparison": {
            "Baseline_Naive_Lag1": {"MAE": round(b1_mae, 2), "RMSE": round(b1_rmse, 2), "WAPE": round(b1_wape, 2)},
            "Baseline_Rolling_7d": {"MAE": round(b2_mae, 2), "RMSE": round(b2_rmse, 2), "WAPE": round(b2_wape, 2)},
            "Random_Forest_ML": {"MAE": round(rf_mae, 2), "RMSE": round(rf_rmse, 2), "WAPE": round(rf_wape, 2)}
        },
        "test_performance": {
            "MAE": round(test_mae, 2),
            "RMSE": round(test_rmse, 2),
            "WAPE": round(test_wape, 2)
        }
    }

    os.makedirs("models", exist_ok=True)
    with open("models/model_metrics.json", "w") as f:
        json.dump(metrics_summary, f, indent=2)

    print("Model metrics saved to models/model_metrics.json")
    return model_rf, metrics_summary

if __name__ == "__main__":
    spark = get_spark_session("demand-forecasting-training")
    try:
        train_and_evaluate(spark, "data/gold/sales_gold", "models/rf_demand_model")
    finally:
        spark.stop()
