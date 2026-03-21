"""silver_ingestion.py content for Phase 4."""


def get() -> str:
    return """\
#!/usr/bin/env python3
\"\"\"
silver_ingestion.py
Phase 4 -- Silver Layer ingestion.

Reads raw Debezium Parquet (PostgreSQL) and JSON (MongoDB) from MinIO,
deduplicates by (merge_key, ts_ms DESC), writes Delta tables to
s3a://orderflow-silver/delta/{entity}/.

Usage:
    spark-submit silver_ingestion.py --entity all
    spark-submit silver_ingestion.py --entity orders
\"\"\"

import argparse
import os
import sys

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DecimalType, LongType, DoubleType

MINIO_ENDPOINT = "http://minio.spark.svc.cluster.local:9000"
RAW_BUCKET     = "s3a://orderflow-raw"
SILVER_BUCKET  = "s3a://orderflow-silver"


def get_spark(app_name: str) -> SparkSession:
    \"\"\"Build a SparkSession with Delta Lake + S3A/MinIO config.\"\"\"
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


def _dedup(df, merge_key: str):
    \"\"\"Keep the row with the highest ts_ms per merge_key.\"\"\"
    from pyspark.sql.window import Window
    w = Window.partitionBy(merge_key).orderBy(F.col("ts_ms").desc())
    return (
        df.withColumn("_rn", F.row_number().over(w))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )


def ingest_orders(spark: SparkSession) -> None:
    \"\"\"Orders: id, status, total_amount (Decimal), timestamps, is_deleted.\"\"\"
    raw = spark.read.parquet(
        f"{RAW_BUCKET}/topics/orderflow.public.orders/partition=*/*.snappy.parquet"
    )
    df = (
        raw.select(
            F.col("after_id").alias("id"),
            F.col("after_status").alias("status"),
            F.col("after_customer_id").alias("customer_id"),
            F.col("after_restaurant_id").alias("restaurant_id"),
            F.col("after_driver_id").alias("driver_id"),
            F.col("after_total_amount").cast(DecimalType(10, 2)).alias("total_amount"),
            F.to_timestamp(F.col("after_created_at")).alias("created_at"),
            F.to_timestamp(F.col("after_updated_at")).alias("updated_at"),
            F.when(F.col("op") == "d", True).otherwise(False).alias("is_deleted"),
            F.col("op").alias("_source_op"),
            F.col("ts_ms"),
        )
        .filter(F.col("id").isNotNull())
    )
    df = _dedup(df, "id").withColumn("_ingested_at", F.current_timestamp())
    df.write.format("delta").mode("overwrite").save(f"{SILVER_BUCKET}/delta/orders")
    print(f"[silver_ingestion] orders written")


def ingest_users(spark: SparkSession) -> None:
    \"\"\"Users: id, name, email, phone, city, timestamps.\"\"\"
    raw = spark.read.parquet(
        f"{RAW_BUCKET}/topics/orderflow.public.users/partition=*/*.snappy.parquet"
    )
    df = (
        raw.select(
            F.col("after_id").alias("id"),
            F.col("after_name").alias("name"),
            F.col("after_email").alias("email"),
            F.col("after_phone").alias("phone"),
            F.col("after_city").alias("city"),
            F.to_timestamp(F.col("after_created_at")).alias("created_at"),
            F.to_timestamp(F.col("after_updated_at")).alias("updated_at"),
            F.when(F.col("op") == "d", True).otherwise(False).alias("is_deleted"),
            F.col("op").alias("_source_op"),
            F.col("ts_ms"),
        )
        .filter(F.col("id").isNotNull())
    )
    df = _dedup(df, "id").withColumn("_ingested_at", F.current_timestamp())
    df.write.format("delta").mode("overwrite").save(f"{SILVER_BUCKET}/delta/users")
    print(f"[silver_ingestion] users written")


def ingest_restaurants(spark: SparkSession) -> None:
    \"\"\"Restaurants: id, name, cuisine, city, rating, commission_rate.\"\"\"
    raw = spark.read.parquet(
        f"{RAW_BUCKET}/topics/orderflow.public.restaurants/partition=*/*.snappy.parquet"
    )
    df = (
        raw.select(
            F.col("after_id").alias("id"),
            F.col("after_name").alias("name"),
            F.col("after_cuisine").alias("cuisine"),
            F.col("after_city").alias("city"),
            F.col("after_rating").cast(DoubleType()).alias("rating"),
            F.col("after_commission_rate").cast(DoubleType()).alias("commission_rate"),
            F.to_timestamp(F.col("after_created_at")).alias("created_at"),
            F.to_timestamp(F.col("after_updated_at")).alias("updated_at"),
            F.when(F.col("op") == "d", True).otherwise(False).alias("is_deleted"),
            F.col("op").alias("_source_op"),
            F.col("ts_ms"),
        )
        .filter(F.col("id").isNotNull())
    )
    df = _dedup(df, "id").withColumn("_ingested_at", F.current_timestamp())
    df.write.format("delta").mode("overwrite").save(f"{SILVER_BUCKET}/delta/restaurants")
    print(f"[silver_ingestion] restaurants written")


def ingest_drivers(spark: SparkSession) -> None:
    \"\"\"Drivers: id, name, phone, city, rating, vehicle_type.\"\"\"
    raw = spark.read.parquet(
        f"{RAW_BUCKET}/topics/orderflow.public.drivers/partition=*/*.snappy.parquet"
    )
    df = (
        raw.select(
            F.col("after_id").alias("id"),
            F.col("after_name").alias("name"),
            F.col("after_phone").alias("phone"),
            F.col("after_city").alias("city"),
            F.col("after_rating").cast(DoubleType()).alias("rating"),
            F.col("after_vehicle_type").alias("vehicle_type"),
            F.to_timestamp(F.col("after_created_at")).alias("created_at"),
            F.to_timestamp(F.col("after_updated_at")).alias("updated_at"),
            F.when(F.col("op") == "d", True).otherwise(False).alias("is_deleted"),
            F.col("op").alias("_source_op"),
            F.col("ts_ms"),
        )
        .filter(F.col("id").isNotNull())
    )
    df = _dedup(df, "id").withColumn("_ingested_at", F.current_timestamp())
    df.write.format("delta").mode("overwrite").save(f"{SILVER_BUCKET}/delta/drivers")
    print(f"[silver_ingestion] drivers written")


def _bson_ts(col_expr):
    \"\"\"Parse BSON {\"$date\": millis} -> timestamp.\"\"\"
    millis = F.get_json_object(col_expr, "$.$date").cast(LongType())
    return (millis / 1000).cast("timestamp")


def ingest_user_events(spark: SparkSession) -> None:
    \"\"\"user_events: double-serialised JSON after field, V1/V2/V3 schema.\"\"\"
    raw = spark.read.json(
        f"{RAW_BUCKET}/topics/mongo.foodtech.user_events/partition=*/*.json"
    )
    a = F.col("after")
    df = (
        raw.filter(F.col("op") != "d")
        .select(
            F.get_json_object(a, "$._id").alias("event_id"),
            F.get_json_object(a, "$.event_type").alias("event_type"),
            F.get_json_object(a, "$.schema_version").cast("int").alias("schema_version"),
            F.get_json_object(a, "$.user_id").cast("long").alias("user_id"),
            _bson_ts(F.get_json_object(a, "$.timestamp")).alias("event_timestamp"),
            F.get_json_object(a, "$.session_id").alias("session_id"),
            F.get_json_object(a, "$.device_type").alias("device_type"),
            F.get_json_object(a, "$.app_version").alias("app_version"),
            F.get_json_object(a, "$.location.lat").cast(DoubleType()).alias("location_lat"),
            F.get_json_object(a, "$.location.lng").cast(DoubleType()).alias("location_lng"),
            F.col("ts_ms"),
            F.col("op").alias("_source_op"),
        )
        .filter(F.col("event_id").isNotNull())
    )
    df = _dedup(df, "event_id").withColumn("_ingested_at", F.current_timestamp())
    df.write.format("delta").mode("overwrite").save(f"{SILVER_BUCKET}/delta/user_events")
    print(f"[silver_ingestion] user_events written")


def ingest_delivery_updates(spark: SparkSession) -> None:
    \"\"\"delivery_updates: order_id, driver_id, status, lat/lng, timestamp.\"\"\"
    raw = spark.read.json(
        f"{RAW_BUCKET}/topics/mongo.foodtech.delivery_updates/partition=*/*.json"
    )
    a = F.col("after")
    df = (
        raw.filter(F.col("op") != "d")
        .select(
            F.get_json_object(a, "$._id").alias("update_id"),
            F.get_json_object(a, "$.order_id").cast("long").alias("order_id"),
            F.get_json_object(a, "$.driver_id").cast("long").alias("driver_id"),
            F.get_json_object(a, "$.status").alias("status"),
            F.get_json_object(a, "$.location.lat").cast(DoubleType()).alias("location_lat"),
            F.get_json_object(a, "$.location.lng").cast(DoubleType()).alias("location_lng"),
            F.get_json_object(a, "$.location.accuracy").cast(DoubleType()).alias("location_accuracy"),
            _bson_ts(F.get_json_object(a, "$.timestamp")).alias("event_timestamp"),
            F.col("ts_ms"),
            F.col("op").alias("_source_op"),
        )
        .filter(F.col("update_id").isNotNull())
    )
    df = _dedup(df, "update_id").withColumn("_ingested_at", F.current_timestamp())
    df.write.format("delta").mode("overwrite").save(
        f"{SILVER_BUCKET}/delta/delivery_updates"
    )
    print(f"[silver_ingestion] delivery_updates written")


ENTITY_MAP = {
    "orders":           ingest_orders,
    "users":            ingest_users,
    "restaurants":      ingest_restaurants,
    "drivers":          ingest_drivers,
    "user_events":      ingest_user_events,
    "delivery_updates": ingest_delivery_updates,
}


def main():
    parser = argparse.ArgumentParser(description="Silver ingestion job")
    parser.add_argument("--entity", required=True, help="Entity name or 'all'")
    args = parser.parse_args()
    spark = get_spark(f"silver_ingestion_{args.entity}")
    entities = list(ENTITY_MAP) if args.entity == "all" else [args.entity]
    if args.entity not in ("all",) and args.entity not in ENTITY_MAP:
        print(f"[ERROR] Unknown entity: {args.entity}", file=sys.stderr)
        sys.exit(1)
    for entity in entities:
        print(f"[silver_ingestion] Starting: {entity}")
        ENTITY_MAP[entity](spark)
    spark.stop()


if __name__ == "__main__":
    main()
"""
