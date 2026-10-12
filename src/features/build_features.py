"""
Phase 2: Feature Engineering & Gold Layer Dataset Creation
Generates leakage-free time-series features using PySpark Window specifications:
- Temporal calendar attributes: day_of_week, day_of_month, month, is_weekend
- Lag features: demand_lag_1, demand_lag_7, demand_lag_14, demand_lag_28
- Rolling features: rolling_demand_mean_7, rolling_demand_mean_14, rolling_demand_mean_28
- Price context: price_to_competitor_ratio, is_discounted
- Business target: 7-day cumulative future demand (days t+1 to t+7)
  Target formula: y_t = sum_{i=1..7} Demand_{t+i}
"""

import sys
import os
from pyspark.sql import Window
from pyspark.sql import functions as F

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.common.spark_utils import get_spark_session

def build_gold_features(spark, silver_path: str, gold_path: str):
    print(f"--- [Gold Layer] Building feature set from {silver_path} ---")
    df = spark.read.parquet(silver_path)

    # Window partitioned by store and product, sorted strictly chronologically by date
    sp_window = Window.partitionBy("store_id", "product_id").orderBy("date")

    # 1. Calendar / Temporal features
    featured_df = (
        df
        .withColumn("day_of_week", F.dayofweek("date"))
        .withColumn("day_of_month", F.dayofmonth("date"))
        .withColumn("month", F.month("date"))
        .withColumn("is_weekend", F.when(F.col("day_of_week").isin([1, 7]), 1).otherwise(0))
    )

    # 2. Lag features (Information strictly from previous days)
    featured_df = (
        featured_df
        .withColumn("demand_lag_1", F.lag("demand", 1).over(sp_window))
        .withColumn("demand_lag_7", F.lag("demand", 7).over(sp_window))
        .withColumn("demand_lag_14", F.lag("demand", 14).over(sp_window))
        .withColumn("demand_lag_28", F.lag("demand", 28).over(sp_window))
    )

    # 3. Rolling window features (CRITICAL: exclude current day t to prevent target leakage: rows between -K and -1)
    rolling_7 = sp_window.rowsBetween(-7, -1)
    rolling_14 = sp_window.rowsBetween(-14, -1)
    rolling_28 = sp_window.rowsBetween(-28, -1)

    featured_df = (
        featured_df
        .withColumn("rolling_demand_mean_7", F.round(F.avg("demand").over(rolling_7), 2))
        .withColumn("rolling_demand_mean_14", F.round(F.avg("demand").over(rolling_14), 2))
        .withColumn("rolling_demand_mean_28", F.round(F.avg("demand").over(rolling_28), 2))
    )

    # 4. Pricing & Promo context
    featured_df = (
        featured_df
        .withColumn(
            "price_to_comp_ratio",
            F.round(
                F.when(
                    (F.col("competitor_pricing").isNotNull()) & (F.col("competitor_pricing") > 0),
                    F.col("price") / F.col("competitor_pricing")
                ).otherwise(1.0),
                4
            )
        )
        .withColumn("is_discounted", F.when(F.col("discount") > 0, 1).otherwise(0))
    )

    # 5. Build Primary Target: Next 7-day cumulative demand (rows between 1 and 7)
    # y_t = sum(D_{t+1} ... D_{t+7})
    target_7d = sp_window.rowsBetween(1, 7)
    # Also next-day target for single-step baseline
    target_1d = sp_window.rowsBetween(1, 1)

    featured_df = (
        featured_df
        .withColumn("target_demand_next_7d", F.sum("demand").over(target_7d))
        .withColumn("target_demand_next_1d", F.sum("demand").over(target_1d))
        # Count future rows to ensure a complete 7-day future window exists
        .withColumn("future_window_count", F.count("demand").over(target_7d))
    )

    # Filter out warmup periods (where 28-day lags are null) and terminal rows (where future 7-day target is incomplete)
    valid_gold_df = (
        featured_df
        .filter(
            F.col("demand_lag_28").isNotNull() &
            F.col("rolling_demand_mean_28").isNotNull() &
            (F.col("future_window_count") == 7)
        )
        .drop("future_window_count")
    )

    total_valid = valid_gold_df.count()
    print(f"[Gold Layer] Successfully engineered features. Retained {total_valid} leakage-free records.")
    print(f"[Gold Layer] Writing Gold dataset to {gold_path}...")
    valid_gold_df.write.mode("overwrite").parquet(gold_path)
    print("[Gold Layer] Write complete.")
    return valid_gold_df

if __name__ == "__main__":
    spark = get_spark_session("feature-engineering-gold")
    try:
        build_gold_features(spark, "data/silver/sales_silver", "data/gold/sales_gold")
    finally:
        spark.stop()
