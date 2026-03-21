"""ClickHouse DDL for Phase 7: gold.dag_run_log and gold.schema_drift_log tables."""


def dag_run_log_sql() -> str:
    return """\
-- clickhouse/gold/13_dag_run_log.sql
-- Phase 7: DAG run telemetry log table.
-- Populated by the dag_telemetry_listener Airflow plugin on every task
-- success or failure event. Never written from DAGs directly.
CREATE TABLE IF NOT EXISTS gold.dag_run_log
(
    event_timestamp  DateTime          DEFAULT now(),
    dag_id           String,
    run_id           String,
    task_id          String,
    operator         String,
    state            String,        -- 'success' | 'failed'
    duration_seconds Float64,
    execution_date   DateTime,
    hostname         String
)
ENGINE = MergeTree()
ORDER BY (event_timestamp, dag_id, task_id)
SETTINGS index_granularity = 8192;
"""


def schema_drift_log_sql() -> str:
    return """\
-- clickhouse/gold/14_schema_drift_log.sql
-- Phase 7: Schema drift detection log table.
-- Populated by orderflow_schema_drift DAG (Phase 6) and the telemetry
-- listener plugin when it detects a schema-drift xcom key on a task.
CREATE TABLE IF NOT EXISTS gold.schema_drift_log
(
    checked_at       DateTime          DEFAULT now(),
    dag_id           String,
    run_id           String,
    entity           String,
    drift_detected   UInt8,
    added_columns    String,
    removed_columns  String,
    type_changes     String
)
ENGINE = MergeTree()
ORDER BY (checked_at, entity)
SETTINGS index_granularity = 8192;
"""
