from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .master("local[2]")
    .appName("inspect-sales-data")
    .getOrCreate()
)

try:
    sales = (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .csv("data/raw/sales_data.csv")
    )

    print("Columns and data types:")
    sales.printSchema()

    print("Row count:", sales.count())

    print("First five rows:")
    sales.show(5, truncate=False)


    from pyspark.sql import functions as F

    null_counts = sales.select([
        F.sum(F.col(f"`{column}`").isNull().cast("int")).alias(column)
        for column in sales.columns
    ]).first().asDict()

    print("Missing values per column:", null_counts)
    print("Duplicate rows:", sales.count() - sales.dropDuplicates().count())

    date_range = sales.select(
        F.min("Date").alias("first_date"),
        F.max("Date").alias("last_date")
    ).first()

    print("Date range:", date_range["first_date"], "to", date_range["last_date"])
    print("Unique stores:", sales.select("Store ID").distinct().count())
    print("Unique products:", sales.select("Product ID").distinct().count())


finally:
    spark.stop()