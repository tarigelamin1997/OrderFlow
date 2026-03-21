"""Root config files for dbt/orderflow_spark/ project."""


def dbt_project_yml() -> str:
    return """\
# dbt/orderflow_spark/dbt_project.yml
# Phase 5 -- dbt-spark project running inside the Airflow pod via SparkSession.
# Python models (py_*.py) execute natively within the active SparkSession.
name: orderflow_spark
version: "1.0.0"
config-version: 2

profile: orderflow_spark

model-paths:   ["models"]
macro-paths:   ["macros"]
target-path:   "target"
clean-targets: ["target", "dbt_packages"]

models:
  orderflow_spark:
    staging:
      +materialized: view
    +materialized: table
"""


def packages_yml() -> str:
    return """\
# dbt/orderflow_spark/packages.yml
# No additional packages required for the spark project.
packages: []
"""


def profiles_yml() -> str:
    return """\
# dbt/orderflow_spark/profiles.yml
# Uses dbt-spark session method: attaches to an existing SparkSession.
# SparkSession is pre-configured by the Airflow DAG before dbt run is invoked.
# S3A credentials are injected at SparkSession creation time via server_side_parameters.
orderflow_spark:
  target: dev
  outputs:
    dev:
      type: spark
      method: session
      schema: "{{ env_var('DBT_SPARK_SCHEMA', 'dbt_spark_dev') }}"
      host: localhost
      server_side_parameters:
        spark.sql.extensions: "io.delta.sql.DeltaSparkSessionExtension"
        spark.sql.catalog.spark_catalog: "org.apache.spark.sql.delta.catalog.DeltaCatalog"
        spark.hadoop.fs.s3a.endpoint: "{{ env_var('MINIO_ENDPOINT', 'http://minio.spark.svc.cluster.local:9000') }}"
        spark.hadoop.fs.s3a.access.key: "{{ env_var('MINIO_ACCESS_KEY', 'minioadmin') }}"
        spark.hadoop.fs.s3a.secret.key: "{{ env_var('MINIO_SECRET_KEY', 'minioadmin') }}"
        spark.hadoop.fs.s3a.path.style.access: "true"
        spark.hadoop.fs.s3a.impl: "org.apache.hadoop.fs.s3a.S3AFileSystem"
"""


def stg_delta_orders_sql() -> str:
    return """\
-- dbt/orderflow_spark/models/staging/stg_delta_orders.sql
-- Phase 5 -- staging view over Delta Silver orders table in MinIO.
{{ config(materialized='view') }}

SELECT
    id                  AS order_id,
    user_id,
    restaurant_id,
    driver_id,
    status,
    CAST(total_amount AS DECIMAL(10,2)) AS total_amount,
    created_at_dt,
    updated_at_dt,
    is_deleted,
    _silver_at
FROM delta.`s3a://orderflow-silver/delta/orders/`
WHERE is_deleted = false
"""


def stg_delta_user_events_sql() -> str:
    return """\
-- dbt/orderflow_spark/models/staging/stg_delta_user_events.sql
-- Phase 5 -- staging view over Delta Silver user_events table in MinIO.
{{ config(materialized='view') }}

SELECT
    event_id,
    user_id,
    event_type,
    page,
    session_id,
    device,
    os,
    event_timestamp,
    schema_version,
    _silver_at
FROM delta.`s3a://orderflow-silver/delta/user_events/`
"""


def macro_generate_schema_name_sql() -> str:
    return """\
-- dbt/orderflow_spark/macros/generate_schema_name.sql
-- Phase 5 -- Override dbt default schema resolution for Spark project.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema | trim }}
    {%- endif -%}
{%- endmacro %}
"""
