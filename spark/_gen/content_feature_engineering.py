"""feature_engineering.py content for Phase 4."""


def get() -> str:
    return """\
#!/usr/bin/env python3
\"\"\"
feature_engineering.py
Phase 4 -- Feature Engineering.

Reads Delta Silver tables from MinIO, writes feature Delta tables to
s3a://orderflow-silver/delta/features/{feature}/.

Features: demand_by_zone, driver_efficiency, restaurant_performance,
          user_cohort_behavior, peak_hour_demand

Usage:
    spark-submit feature_engineering.py --feature all
\"\"\"

import argparse
import os
import sys

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DecimalType

MINIO_ENDPOINT = "http://minio.spark.svc.cluster.local:9000"
SILVER_BUCKET  = "s3a://orderflow-silver"


def get_spark(app_name: str) -> SparkSession:
    \"\"\"SparkSession with Delta Lake and S3A/MinIO config.\"\"\"
    access_key = os.environ["MINIO_ACCESS_KEY"]
    secret_key = os.environ["MINIO_SECRET_KEY"]
    spark = (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def _silver(spark, entity):
    return spark.read.format("delta").load(f"{SILVER_BUCKET}/delta/{entity}")


def _save(df, feature):
    path = f"{SILVER_BUCKET}/delta/features/{feature}"
    df.withColumn("_computed_at", F.current_timestamp()) \\
      .write.format("delta").mode("overwrite").save(path)
    print(f"[feature_engineering] {feature} written to {path}")


def feat_demand_by_zone(spark):
    \"\"\"order count & GMV by (city, date) via orders JOIN restaurants.\"\"\"
    orders = _silver(spark, "orders").filter(F.col("is_deleted") == False)
    rests  = _silver(spark, "restaurants").select("id", "city")
    df = (
        orders.join(rests, orders["restaurant_id"] == rests["id"], "left")
        .select(rests["city"], F.to_date(orders["created_at"]).alias("order_date"),
                orders["total_amount"])
        .groupBy("city", "order_date")
        .agg(F.count("*").alias("order_count"),
             F.sum("total_amount").cast(DecimalType(14, 2)).alias("total_gmv"))
    )
    _save(df, "demand_by_zone")


def feat_driver_efficiency(spark):
    \"\"\"delivered order stats by (driver_id, date).\"\"\"
    orders = _silver(spark, "orders").filter(
        (F.col("is_deleted") == False) & (F.col("status") == "delivered")
    )
    df = (
        orders.select(F.col("driver_id"),
                      F.to_date(F.col("created_at")).alias("order_date"),
                      F.col("total_amount"))
        .groupBy("driver_id", "order_date")
        .agg(F.count("*").alias("deliveries_completed"),
             F.avg("total_amount").cast(DecimalType(10, 2)).alias("avg_order_value"),
             F.sum("total_amount").cast(DecimalType(14, 2)).alias("total_revenue"))
    )
    _save(df, "driver_efficiency")


def feat_restaurant_performance(spark):
    \"\"\"order count, revenue by (restaurant_id, date).\"\"\"
    orders = _silver(spark, "orders").filter(F.col("is_deleted") == False)
    df = (
        orders.select(F.col("restaurant_id"),
                      F.to_date(F.col("created_at")).alias("order_date"),
                      F.col("total_amount"))
        .groupBy("restaurant_id", "order_date")
        .agg(F.count("*").alias("order_count"),
             F.sum("total_amount").cast(DecimalType(14, 2)).alias("total_revenue"),
             F.avg("total_amount").cast(DecimalType(10, 2)).alias("avg_order_value"))
    )
    _save(df, "restaurant_performance")


def feat_user_cohort_behavior(spark):
    \"\"\"order activity by user cohort = YYYY-MM of signup.\"\"\"
    users  = _silver(spark, "users").select("id", "created_at")
    orders = _silver(spark, "orders").filter(F.col("is_deleted") == False)
    df = (
        orders.join(users, orders["customer_id"] == users["id"], "left")
        .select(
            F.date_format(users["created_at"], "yyyy-MM").alias("signup_cohort"),
            orders["customer_id"],
            orders["total_amount"],
            F.to_date(orders["created_at"]).alias("order_date"),
        )
        .groupBy("signup_cohort", "order_date")
        .agg(F.countDistinct("customer_id").alias("active_users"),
             F.count("*").alias("order_count"),
             F.sum("total_amount").cast(DecimalType(14, 2)).alias("total_gmv"))
    )
    _save(df, "user_cohort_behavior")


def feat_peak_hour_demand(spark):
    \"\"\"order volume by (city, hour_of_day) via orders JOIN restaurants.\"\"\"
    orders = _silver(spark, "orders").filter(F.col("is_deleted") == False)
    rests  = _silver(spark, "restaurants").select("id", "city")
    df = (
        orders.join(rests, orders["restaurant_id"] == rests["id"], "left")
        .select(rests["city"],
                F.hour(orders["created_at"]).alias("hour_of_day"),
                orders["total_amount"])
        .groupBy("city", "hour_of_day")
        .agg(F.count("*").alias("order_count"),
             F.sum("total_amount").cast(DecimalType(14, 2)).alias("total_gmv"))
        .orderBy("city", "hour_of_day")
    )
    _save(df, "peak_hour_demand")


FEATURE_MAP = {
    "demand_by_zone":         feat_demand_by_zone,
    "driver_efficiency":      feat_driver_efficiency,
    "restaurant_performance": feat_restaurant_performance,
    "user_cohort_behavior":   feat_user_cohort_behavior,
    "peak_hour_demand":       feat_peak_hour_demand,
}


def main():
    parser = argparse.ArgumentParser(description="Feature engineering job")
    parser.add_argument("--feature", required=True, help="Feature name or 'all'")
    args = parser.parse_args()
    spark = get_spark(f"feature_engineering_{args.feature}")
    features = list(FEATURE_MAP) if args.feature == "all" else [args.feature]
    if args.feature not in ("all",) and args.feature not in FEATURE_MAP:
        print(f"[ERROR] Unknown feature: {args.feature}", file=sys.stderr)
        sys.exit(1)
    for feat in features:
        print(f"[feature_engineering] Starting: {feat}")
        FEATURE_MAP[feat](spark)
    spark.stop()


if __name__ == "__main__":
    main()
"""
