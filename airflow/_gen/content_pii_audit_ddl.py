"""ClickHouse DDL for Phase 6: gold.pii_audit_log table."""


def pii_audit_log_sql() -> str:
    return """\
-- clickhouse/gold/12_pii_audit_log.sql
-- Phase 6: PII audit log table.
-- Records results of every PII compliance check run by orderflow_pii_audit DAG.
CREATE TABLE IF NOT EXISTS gold.pii_audit_log
(
    audit_timestamp  DateTime          DEFAULT now(),
    dag_id           String,
    task_id          String,
    entity           String,
    layer            String,
    check_type       String,
    passed           UInt8,
    sample_count     UInt32,
    failure_count    UInt32,
    failure_detail   String
)
ENGINE = MergeTree()
ORDER BY (audit_timestamp, entity)
SETTINGS index_granularity = 8192;
"""
