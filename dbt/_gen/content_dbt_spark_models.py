"""Python model files for dbt/orderflow_spark/models/."""


def py_feature_validation() -> str:
    return """\
# dbt/orderflow_spark/models/py_feature_validation.py
# Phase 5 -- Python model: validate Phase 4 feature tables in Delta.
# Checks row counts and key columns; raises ValueError if validation fails.
# dbt-spark Python models receive a 'dbt' helper and a SparkSession.
import pyspark.sql.functions as F


def model(dbt, spark):
    # Configure -- materialise as Delta table
    dbt.config(materialized="table")

    features = [
        ("demand_by_zone",           ["zone", "order_count"]),
        ("driver_efficiency",        ["driver_id", "deliveries"]),
        ("restaurant_performance",   ["restaurant_id", "order_count"]),
        ("user_cohort_behavior",     ["user_id", "total_orders"]),
        ("peak_hour_demand",         ["hour_of_day", "order_count"]),
    ]

    results = []
    for feature_name, required_cols in features:
        path = f"s3a://orderflow-silver/delta/features/{feature_name}/"
        try:
            df = spark.read.format("delta").load(path)
            row_count = df.count()
            missing_cols = [c for c in required_cols if c not in df.columns]
            status = "PASS" if row_count > 0 and not missing_cols else "FAIL"
            detail = f"rows={row_count}, missing_cols={missing_cols}"
        except Exception as exc:  # noqa: BLE001 -- log all errors in validation
            status = "FAIL"
            detail = str(exc)

        results.append({
            "feature_name": feature_name,
            "status": status,
            "detail": detail,
        })

    schema = "feature_name STRING, status STRING, detail STRING"
    return spark.createDataFrame(results, schema=schema)
"""


def py_driver_score() -> str:
    return """\
# dbt/orderflow_spark/models/py_driver_score.py
# Phase 5 -- Python model: compute composite driver scores from Delta features.
# Score = weighted combination of delivery rate, rating, and order volume.
import pyspark.sql.functions as F
from pyspark.sql.window import Window


def model(dbt, spark):
    dbt.config(materialized="table")

    driver_df = (
        spark.read.format("delta")
        .load("s3a://orderflow-silver/delta/features/driver_efficiency/")
    )

    # Normalise key metrics to [0, 1] using window-based min-max scaling
    w_all = Window.rowsBetween(Window.unboundedPreceding, Window.unboundedFollowing)

    scored = (
        driver_df
        .withColumn(
            "delivery_rate_norm",
            (F.col("delivery_rate") - F.min("delivery_rate").over(w_all))
            / (F.max("delivery_rate").over(w_all)
               - F.min("delivery_rate").over(w_all) + 0.001)
        )
        .withColumn(
            "rating_norm",
            (F.col("avg_rating") - F.min("avg_rating").over(w_all))
            / (F.max("avg_rating").over(w_all)
               - F.min("avg_rating").over(w_all) + 0.001)
        )
        .withColumn(
            "volume_norm",
            (F.col("deliveries") - F.min("deliveries").over(w_all))
            / (F.max("deliveries").over(w_all)
               - F.min("deliveries").over(w_all) + 0.001)
        )
        # Composite score: 40% delivery rate, 40% rating, 20% volume
        .withColumn(
            "composite_score",
            F.round(
                0.4 * F.col("delivery_rate_norm")
                + 0.4 * F.col("rating_norm")
                + 0.2 * F.col("volume_norm"),
                4
            )
        )
        .select("driver_id", "deliveries", "delivery_rate",
                "avg_rating", "composite_score")
    )

    return scored
"""


def py_demand_features() -> str:
    return """\
# dbt/orderflow_spark/models/py_demand_features.py
# Phase 5 -- Python model: enrich demand-by-zone features with time-of-day patterns.
# Joins peak_hour_demand with demand_by_zone to produce a unified demand surface.
import pyspark.sql.functions as F


def model(dbt, spark):
    dbt.config(materialized="table")

    demand_zone = (
        spark.read.format("delta")
        .load("s3a://orderflow-silver/delta/features/demand_by_zone/")
    )
    peak_hour = (
        spark.read.format("delta")
        .load("s3a://orderflow-silver/delta/features/peak_hour_demand/")
    )

    # Aggregate peak demand score per zone by joining on date
    peak_agg = (
        peak_hour
        .groupBy(F.to_date("window_start").alias("demand_date"))
        .agg(
            F.sum("order_count").alias("peak_order_count"),
            F.avg("order_count").alias("avg_hourly_orders"),
            F.max("hour_of_day").alias("peak_hour"),
        )
    )

    enriched = (
        demand_zone
        .join(peak_agg, on="demand_date", how="left")
        .withColumn(
            "demand_intensity",
            F.round(
                F.col("order_count") / (F.col("avg_hourly_orders") + 0.001),
                3
            )
        )
        .select(
            "zone",
            "demand_date",
            "order_count",
            "total_revenue",
            "avg_hourly_orders",
            "peak_hour",
            "demand_intensity",
        )
    )

    return enriched
"""
