"""
Phase 1: Ingestion & Medallion Pipeline (Bronze & Silver)
Reads raw sales CSV, enforces rigorous schema, handles nulls/duplicates,
standardizes column names, and writes partitioned Parquet files to bronze and silver layers.
"""

import sys
import os
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    DoubleType,
    DateType,
    TimestampType
)

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.common.spark_utils import get_spark_session

RAW_SALES_SCHEMA = StructType([
    StructField("Date", DateType(), True),
    StructField("Store ID", StringType(), True),
    StructField("Product ID", StringType(), True),
    StructField("Category", StringType(), True),
    StructField("Region", StringType(), True),
    StructField("Inventory Level", IntegerType(), True),
    StructField("Units Sold", IntegerType(), True),
    StructField("Units Ordered", IntegerType(), True),
    StructField("Price", DoubleType(), True),
    StructField("Discount", IntegerType(), True),
    StructField("Weather Condition", StringType(), True),
    StructField("Promotion", IntegerType(), True),
    StructField("Competitor Pricing", DoubleType(), True),
    StructField("Seasonality", StringType(), True),
    StructField("Epidemic", IntegerType(), True),
    StructField("Demand", IntegerType(), True)
])

def run_bronze_ingestion(spark, input_path: str, bronze_path: str):
    print(f"--- [Bronze Layer] Reading raw CSV from {input_path} ---")
    raw_df = (
        spark.read
        .option("header", "true")
        .schema(RAW_SALES_SCHEMA)
        .csv(input_path)
    )
    
    # Add metadata columns
    bronze_df = (
        raw_df
        .withColumn("ingestion_timestamp", F.current_timestamp())
        .withColumn("source_file", F.lit("sales_data.csv"))
    )
    
    count = bronze_df.count()
    print(f"[Bronze Layer] Ingested {count} records. Writing to {bronze_path}...")
    bronze_df.write.mode("overwrite").parquet(bronze_path)
    print("[Bronze Layer] Write complete.")
    return bronze_df

def run_silver_cleaning(spark, bronze_path: str, silver_path: str):
    print(f"--- [Silver Layer] Cleaning and standardizing from {bronze_path} ---")
    bronze_df = spark.read.parquet(bronze_path)
    
    # 1. Standardize column names (snake_case)
    renamed_df = (
        bronze_df
        .withColumnRenamed("Date", "date")
        .withColumnRenamed("Store ID", "store_id")
        .withColumnRenamed("Product ID", "product_id")
        .withColumnRenamed("Category", "category")
        .withColumnRenamed("Region", "region")
        .withColumnRenamed("Inventory Level", "inventory_level")
        .withColumnRenamed("Units Sold", "units_sold")
        .withColumnRenamed("Units Ordered", "units_ordered")
        .withColumnRenamed("Price", "price")
        .withColumnRenamed("Discount", "discount")
        .withColumnRenamed("Weather Condition", "weather_condition")
        .withColumnRenamed("Promotion", "promotion")
        .withColumnRenamed("Competitor Pricing", "competitor_pricing")
        .withColumnRenamed("Seasonality", "seasonality")
        .withColumnRenamed("Epidemic", "epidemic")
        .withColumnRenamed("Demand", "demand")
    )
    
    # 2. Quality checks: drop duplicates across business keys (date, store_id, product_id)
    deduped_df = renamed_df.dropDuplicates(["date", "store_id", "product_id"])
    
    # 3. Handle nulls and negative quantities
    cleaned_df = (
        deduped_df
        .filter(F.col("date").isNotNull() & F.col("store_id").isNotNull() & F.col("product_id").isNotNull())
        .withColumn("inventory_level", F.when(F.col("inventory_level") < 0, 0).otherwise(F.col("inventory_level")))
        .withColumn("units_sold", F.when(F.col("units_sold") < 0, 0).otherwise(F.col("units_sold")))
        .withColumn("units_ordered", F.when(F.col("units_ordered") < 0, 0).otherwise(F.col("units_ordered")))
        .withColumn("demand", F.when(F.col("demand") < 0, 0).otherwise(F.col("demand")))
        .withColumn("price", F.when(F.col("price") < 0, 0.0).otherwise(F.col("price")))
    )
    
    silver_count = cleaned_df.count()
    print(f"[Silver Layer] Validated {silver_count} clean records. Writing to {silver_path}...")
    cleaned_df.write.mode("overwrite").parquet(silver_path)
    print("[Silver Layer] Write complete.")
    return cleaned_df

if __name__ == "__main__":
    spark = get_spark_session("bronze-silver-ingestion")
    try:
        run_bronze_ingestion(spark, "data/raw/sales_data.csv", "data/bronze/sales_bronze")
        run_silver_cleaning(spark, "data/bronze/sales_bronze", "data/silver/sales_silver")
    finally:
        spark.stop()
