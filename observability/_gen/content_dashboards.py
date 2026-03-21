"""Content for the five Grafana dashboard JSON files (Phase 7)."""

import json

_DS = {
    "type": "vertamedia-clickhouse-datasource",
    "uid": "PDEE91DDB90597936",
}

_BASE_PANEL = {
    "datasource": _DS,
    "fieldConfig": {"defaults": {}, "overrides": []},
    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
    "options": {},
    "pluginVersion": "10.0.0",
}


def _panel(pid: int, title: str, sql: str, viz: str, x: int, y: int) -> dict:
    p = dict(_BASE_PANEL)
    p["id"] = pid
    p["title"] = title
    p["type"] = viz
    p["gridPos"] = {"h": 8, "w": 12, "x": x, "y": y}
    p["datasource"] = _DS
    if viz == "stat":
        p["options"] = {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": "auto",
            "textMode": "auto",
            "colorMode": "value",
        }
    else:
        p["options"] = {"frameIndex": 0, "showHeader": True}
    p["targets"] = [
        {
            "datasource": _DS,
            "format": "table",
            "rawSql": sql,
            "refId": "A",
        }
    ]
    return p


def _dashboard(uid: str, title: str, panels: list) -> dict:
    return {
        "uid": uid,
        "title": title,
        "schemaVersion": 38,
        "version": 1,
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {},
        "templating": {"list": []},
        "annotations": {"list": []},
        "panels": panels,
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "links": [],
        "liveNow": False,
        "tags": ["orderflow"],
        "timezone": "browser",
    }


def pipeline_health_json() -> str:
    panels = [
        _panel(
            1,
            "Task Success Rate (last 6h)",
            (
                "SELECT state, count() AS cnt "
                "FROM gold.dag_run_log "
                "WHERE event_timestamp >= now() - INTERVAL 6 HOUR "
                "GROUP BY state "
                "ORDER BY state"
            ),
            "table",
            0,
            0,
        ),
        _panel(
            2,
            "Failed Tasks (last 6h)",
            (
                "SELECT dag_id, task_id, run_id, event_timestamp "
                "FROM gold.dag_run_log "
                "WHERE state = 'failed' "
                "AND event_timestamp >= now() - INTERVAL 6 HOUR "
                "ORDER BY event_timestamp DESC "
                "LIMIT 50"
            ),
            "table",
            12,
            0,
        ),
        _panel(
            3,
            "Avg Task Duration by DAG (last 24h)",
            (
                "SELECT dag_id, round(avg(duration_seconds), 2) AS avg_sec "
                "FROM gold.dag_run_log "
                "WHERE event_timestamp >= now() - INTERVAL 24 HOUR "
                "GROUP BY dag_id "
                "ORDER BY avg_sec DESC"
            ),
            "table",
            0,
            8,
        ),
    ]
    return json.dumps(
        _dashboard("of-pipeline-health", "OrderFlow — Pipeline Health", panels),
        indent=2,
    )


def data_quality_json() -> str:
    panels = [
        _panel(
            1,
            "PII Audit Failures (last 7d)",
            (
                "SELECT entity, check_type, sum(failure_count) AS total_failures "
                "FROM gold.pii_audit_log "
                "WHERE audit_timestamp >= now() - INTERVAL 7 DAY "
                "GROUP BY entity, check_type "
                "ORDER BY total_failures DESC"
            ),
            "table",
            0,
            0,
        ),
        _panel(
            2,
            "Schema Drift Events (last 7d)",
            (
                "SELECT checked_at, entity, added_columns, removed_columns, type_changes "
                "FROM gold.schema_drift_log "
                "WHERE drift_detected = 1 "
                "AND checked_at >= now() - INTERVAL 7 DAY "
                "ORDER BY checked_at DESC "
                "LIMIT 50"
            ),
            "table",
            12,
            0,
        ),
        _panel(
            3,
            "DAG Quality Gate Runs (last 24h)",
            (
                "SELECT dag_id, task_id, state, event_timestamp "
                "FROM gold.dag_run_log "
                "WHERE dag_id = 'orderflow_quality_gate' "
                "AND event_timestamp >= now() - INTERVAL 24 HOUR "
                "ORDER BY event_timestamp DESC"
            ),
            "table",
            0,
            8,
        ),
    ]
    return json.dumps(
        _dashboard("of-data-quality", "OrderFlow — Data Quality", panels),
        indent=2,
    )


def clickhouse_ops_json() -> str:
    panels = [
        _panel(
            1,
            "Slow Queries (>5s, last 1h)",
            (
                "SELECT query_id, left(query, 80) AS query_preview, "
                "query_duration_ms, read_rows "
                "FROM system.query_log "
                "WHERE query_duration_ms > 5000 "
                "AND event_time >= now() - INTERVAL 1 HOUR "
                "AND type = 'QueryFinish' "
                "ORDER BY query_duration_ms DESC "
                "LIMIT 20"
            ),
            "table",
            0,
            0,
        ),
        _panel(
            2,
            "Table Sizes (gold + silver)",
            (
                "SELECT database, table, "
                "formatReadableSize(sum(bytes_on_disk)) AS size_on_disk, "
                "sum(rows) AS total_rows "
                "FROM system.parts "
                "WHERE active = 1 "
                "AND database IN ('gold', 'silver') "
                "GROUP BY database, table "
                "ORDER BY database, table"
            ),
            "table",
            12,
            0,
        ),
        _panel(
            3,
            "Active Mutations",
            (
                "SELECT database, table, mutation_id, "
                "left(command, 60) AS command, is_done "
                "FROM system.mutations "
                "WHERE is_done = 0 "
                "ORDER BY create_time DESC "
                "LIMIT 20"
            ),
            "table",
            0,
            8,
        ),
    ]
    return json.dumps(
        _dashboard("of-clickhouse-ops", "OrderFlow — ClickHouse Operations", panels),
        indent=2,
    )


def business_metrics_json() -> str:
    # Dashboard 4 MUST query dbt_dev__gold (not dbt_staging__gold)
    panels = [
        _panel(
            1,
            "Orders by Status",
            (
                "SELECT status, count() AS order_count "
                "FROM dbt_dev__gold.mart_orders "
                "GROUP BY status "
                "ORDER BY order_count DESC"
            ),
            "table",
            0,
            0,
        ),
        _panel(
            2,
            "Revenue by Restaurant (top 20)",
            (
                "SELECT restaurant_id, "
                "round(sum(total_amount), 2) AS total_revenue "
                "FROM dbt_dev__gold.mart_orders "
                "GROUP BY restaurant_id "
                "ORDER BY total_revenue DESC "
                "LIMIT 20"
            ),
            "table",
            12,
            0,
        ),
        _panel(
            3,
            "Active Drivers",
            (
                "SELECT status, count() AS driver_count "
                "FROM dbt_dev__gold.mart_drivers "
                "GROUP BY status "
                "ORDER BY driver_count DESC"
            ),
            "table",
            0,
            8,
        ),
    ]
    return json.dumps(
        _dashboard(
            "of-business-metrics",
            "OrderFlow — Business Metrics (dbt_dev__gold)",
            panels,
        ),
        indent=2,
    )


def finops_resources_json() -> str:
    panels = [
        _panel(
            1,
            "Total DAG Runs per Day (last 7d)",
            (
                "SELECT toDate(event_timestamp) AS run_date, "
                "dag_id, count() AS runs "
                "FROM gold.dag_run_log "
                "WHERE event_timestamp >= now() - INTERVAL 7 DAY "
                "GROUP BY run_date, dag_id "
                "ORDER BY run_date DESC, runs DESC"
            ),
            "table",
            0,
            0,
        ),
        _panel(
            2,
            "Storage by Database",
            (
                "SELECT database, "
                "formatReadableSize(sum(bytes_on_disk)) AS disk_usage, "
                "sum(rows) AS total_rows "
                "FROM system.parts "
                "WHERE active = 1 "
                "GROUP BY database "
                "ORDER BY sum(bytes_on_disk) DESC"
            ),
            "table",
            12,
            0,
        ),
        _panel(
            3,
            "Task Duration Outliers (>300s, last 7d)",
            (
                "SELECT dag_id, task_id, "
                "round(max(duration_seconds), 1) AS max_sec "
                "FROM gold.dag_run_log "
                "WHERE event_timestamp >= now() - INTERVAL 7 DAY "
                "AND duration_seconds > 300 "
                "GROUP BY dag_id, task_id "
                "ORDER BY max_sec DESC "
                "LIMIT 20"
            ),
            "table",
            0,
            8,
        ),
    ]
    return json.dumps(
        _dashboard(
            "of-finops-resources",
            "OrderFlow — FinOps & Resources",
            panels,
        ),
        indent=2,
    )
