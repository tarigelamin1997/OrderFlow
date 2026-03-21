"""Content for observability/plugins/dag_telemetry_listener.py."""


def dag_telemetry_listener() -> str:
    return '''\
# observability/plugins/dag_telemetry_listener.py
# Phase 7: Airflow listener plugin that writes DAG/task telemetry to ClickHouse.
# Registered automatically by Airflow when placed in the plugins/ directory.
# All exceptions are caught so telemetry never breaks DAG execution.
from __future__ import annotations

import logging
from datetime import datetime

from airflow.listeners import hookimpl
from airflow.plugins_manager import AirflowPlugin

log = logging.getLogger(__name__)

CH_HOST = "clickhouse.clickhouse.svc.cluster.local"
CH_PORT = 9000


def _get_client():
    """Return a clickhouse_driver Client, or None if unavailable."""
    try:
        from clickhouse_driver import Client  # noqa: PLC0415
        return Client(host=CH_HOST, port=CH_PORT)
    except Exception as exc:  # noqa: BLE001
        log.warning("dag_telemetry_listener: cannot connect to ClickHouse: %s", exc)
        return None


def _write_dag_run_log(task_instance, state: str) -> None:
    """Insert one row into gold.dag_run_log for a task completion event."""
    client = _get_client()
    if client is None:
        return
    try:
        duration = 0.0
        if task_instance.start_date and task_instance.end_date:
            duration = (
                task_instance.end_date - task_instance.start_date
            ).total_seconds()
        exec_date = task_instance.execution_date or datetime.utcnow()
        if hasattr(exec_date, "replace"):
            exec_date = exec_date.replace(tzinfo=None)
        client.execute(
            "INSERT INTO gold.dag_run_log "
            "(event_timestamp, dag_id, run_id, task_id, operator, state, "
            "duration_seconds, execution_date, hostname) "
            "VALUES (now(), %(dag_id)s, %(run_id)s, %(task_id)s, %(operator)s, "
            "%(state)s, %(duration)s, %(exec_date)s, %(hostname)s)",
            {
                "dag_id": str(task_instance.dag_id),
                "run_id": str(task_instance.run_id),
                "task_id": str(task_instance.task_id),
                "operator": str(
                    getattr(task_instance, "operator_name", "unknown")
                ),
                "state": state,
                "duration": duration,
                "exec_date": exec_date,
                "hostname": str(
                    getattr(task_instance, "hostname", "unknown")
                ),
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("dag_telemetry_listener: _write_dag_run_log failed: %s", exc)


def _write_schema_drift_log(task_instance) -> None:
    """If task pushed a schema_drift xcom, persist it to gold.schema_drift_log."""
    try:
        drift_data = task_instance.xcom_pull(
            task_ids=task_instance.task_id, key="schema_drift"
        )
        if not drift_data or not isinstance(drift_data, dict):
            return
        client = _get_client()
        if client is None:
            return
        client.execute(
            "INSERT INTO gold.schema_drift_log "
            "(checked_at, dag_id, run_id, entity, drift_detected, "
            "added_columns, removed_columns, type_changes) "
            "VALUES (now(), %(dag_id)s, %(run_id)s, %(entity)s, "
            "%(drift)s, %(added)s, %(removed)s, %(changes)s)",
            {
                "dag_id": str(task_instance.dag_id),
                "run_id": str(task_instance.run_id),
                "entity": str(drift_data.get("entity", "")),
                "drift": int(drift_data.get("drift_detected", 0)),
                "added": str(drift_data.get("added_columns", "")),
                "removed": str(drift_data.get("removed_columns", "")),
                "changes": str(drift_data.get("type_changes", "")),
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "dag_telemetry_listener: _write_schema_drift_log failed: %s", exc
        )


class OrderFlowTelemetryListener:
    """Airflow listener that records task outcomes to ClickHouse gold tables."""

    @hookimpl
    def on_task_instance_success(self, previous_state, task_instance, session):
        """Called by Airflow after every successful task instance."""
        _write_dag_run_log(task_instance, "success")
        _write_schema_drift_log(task_instance)

    @hookimpl
    def on_task_instance_failed(
        self, previous_state, task_instance, error, session
    ):
        """Called by Airflow after every failed task instance."""
        _write_dag_run_log(task_instance, "failed")


class OrderFlowTelemetryPlugin(AirflowPlugin):
    """Registers the telemetry listener with Airflow\'s plugin system."""

    name = "orderflow_telemetry_plugin"
    listeners = [OrderFlowTelemetryListener()]
'''
