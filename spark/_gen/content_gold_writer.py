"""gold_writer.py content for Phase 4."""


def get() -> str:
    return """\
#!/usr/bin/env python3
\"\"\"
gold_writer.py
Phase 4 -- Gold batch writer.

Reads feature Delta tables from Silver, writes batch rows to ClickHouse
Gold tables via JDBC.

Tables: gold.restaurant_revenue_batch (SummingMergeTree),
        gold.driver_features_batch    (ReplacingMergeTree),
        gold.demand_zone_batch        (SummingMergeTree)

Usage:
    spark-submit gold_writer.py
\"\"\"

import os
import sys

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DecimalType

MINIO_ENDPOINT = "http://minio.spark.svc.cluster.local:9000"
SILVER_BUCKET  = "s3a://orderflow-silver"
CH_JDBC_URL    = "jdbc:clickhouse://clickhouse.clickhouse.svc.cluster.local:8123/gold"
CH_DRIVER      = "com.clickhouse.jdbc.ClickHouseDriver"
CH_USER        = "default"


def get_spark(app_name: str) -> SparkSession:
    \"\"\"SparkSession with Delta Lake + S3A/MinIO config.\"\"\"
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


def _jdbc_write(df, table: str) -> None:
    \"\"\"Append a DataFrame to a ClickHouse table via JDBC.\"\"\"
    (
        df.write.format("jdbc")
        .option("url", CH_JDBC_URL)
        .option("driver", CH_DRIVER)
        .option("dbtable", table)
        .option("user", CH_USER)
        .option("password", os.environ.get("CLICKHOUSE_PASSWORD", ""))
        .mode("append")
        .save()
    )
    print(f"[gold_writer] Written to {table}")


def _feat(spark, feature):
    return spark.read.format("delta").load(
        f"{SILVER_BUCKET}/delta/features/{feature}"
    )


def write_restaurant_revenue_batch(spark):
    \"\"\"gold.restaurant_revenue_batch -- SummingMergeTree.\"\"\"
    ts = F.current_timestamp()
    df = _feat(spark, "restaurant_performance").select(
        F.col("restaurant_id").cast("Int32"),
        F.col("order_date"),
        F.col("order_count").cast("Int64"),
        F.col("total_revenue").cast(DecimalType(14, 2)),
        F.col("avg_order_value").cast(DecimalType(10, 2)),
        ts.alias("_batch_run_at"),
    )
    _jdbc_write(df, "gold.restaurant_revenue_batch")


def write_driver_features_batch(spark):
    \"\"\"gold.driver_features_batch -- ReplacingMergeTree(_batch_run_at).\"\"\"
    ts = F.current_timestamp()
    df = _feat(spark, "driver_efficiency").select(
        F.col("driver_id").cast("Int32"),
        F.col("order_date"),
        F.col("deliveries_completed").cast("Int64"),
        F.col("avg_order_value").cast(DecimalType(10, 2)),
        F.col("total_revenue").cast(DecimalType(14, 2)),
        ts.alias("_batch_run_at"),
    )
    _jdbc_write(df, "gold.driver_features_batch")


def write_demand_zone_batch(spark):
    \"\"\"gold.demand_zone_batch -- SummingMergeTree.\"\"\"
    ts = F.current_timestamp()
    df = _feat(spark, "demand_by_zone").select(
        F.col("city"),
        F.col("order_date"),
        F.col("order_count").cast("Int64"),
        F.col("total_gmv").cast(DecimalType(14, 2)),
        ts.alias("_batch_run_at"),
    )
    _jdbc_write(df, "gold.demand_zone_batch")


def main():
    spark = get_spark("gold_writer")
    try:
        write_restaurant_revenue_batch(spark)
        write_driver_features_batch(spark)
        write_demand_zone_batch(spark)
        print("[gold_writer] All Gold batch tables written successfully.")
    except Exception as exc:
        print(f"[gold_writer] FATAL: {exc}", file=sys.stderr)
        spark.stop()
        sys.exit(1)
    spark.stop()


if __name__ == "__main__":
    main()
"""
