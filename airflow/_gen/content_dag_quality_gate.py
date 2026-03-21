"""DAG content: DAG 5 -- orderflow_quality_gate (@daily)."""

_CH_HOST = "clickhouse.clickhouse.svc.cluster.local"
_VALID_STATUSES = "pending, accepted, picked_up, delivered, cancelled"


def dag_quality_gate() -> str:
    return (
        "# airflow/dags/orderflow_quality_gate.py\n"
        "# Phase 6 -- DAG 5: Daily data-quality gate using Great Expectations checks\n"
        "# embedded as PythonOperators. Checks silver.orders and silver.user_events.\n"
        "from __future__ import annotations\n"
        "\n"
        "import logging\n"
        "from datetime import datetime, timedelta\n"
        "\n"
        "from airflow import DAG\n"
        "from airflow.operators.python import PythonOperator, ShortCircuitOperator\n"
        "\n"
        "log = logging.getLogger(__name__)\n"
        "\n"
        "DEFAULT_ARGS = {\n"
        '    "owner": "orderflow",\n'
        '    "retries": 1,\n'
        '    "retry_delay": timedelta(minutes=5),\n'
        "}\n"
        "\n"
        'VALID_STATUSES = {"pending", "accepted", "picked_up", "delivered", "cancelled"}\n'
        "_CHECK_RESULTS: dict[str, bool] = {}\n"
        "\n"
        f'CH_HOST = "{_CH_HOST}"\n'
        "\n"
        "\n"
        "def _check_orders(**_) -> None:\n"
        "    # Validate silver.orders: row count > 0, total_amount not null, status in valid set.\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "\n"
        "    client = Client(CH_HOST)\n"
        "    passed = True\n"
        "\n"
        '    count = client.execute("SELECT count() FROM silver.orders")[0][0]\n'
        "    if count == 0:\n"
        '        log.error("ge_orders: silver.orders is empty")\n'
        "        passed = False\n"
        "    else:\n"
        '        log.info("ge_orders: silver.orders row count = %d", count)\n'
        "\n"
        "    null_amounts = client.execute(\n"
        '        "SELECT count() FROM silver.orders WHERE total_amount IS NULL OR isNaN(total_amount)"\n'
        "    )[0][0]\n"
        "    if null_amounts > 0:\n"
        '        log.error("ge_orders: %d rows have null/NaN total_amount", null_amounts)\n'
        "        passed = False\n"
        "    else:\n"
        '        log.info("ge_orders: total_amount null check passed")\n'
        "\n"
        "    invalid_statuses = client.execute(\n"
        '        "SELECT count() FROM silver.orders WHERE status NOT IN %(statuses)s",\n'
        '        {"statuses": tuple(VALID_STATUSES)},\n'
        "    )[0][0]\n"
        "    if invalid_statuses > 0:\n"
        '        log.error("ge_orders: %d rows have invalid status values", invalid_statuses)\n'
        "        passed = False\n"
        "    else:\n"
        '        log.info("ge_orders: status values check passed")\n'
        "\n"
        '    _CHECK_RESULTS["ge_orders"] = passed\n'
        "    if not passed:\n"
        '        raise ValueError("ge_orders: one or more quality checks failed -- see logs")\n'
        "\n"
        "\n"
        "def _check_user_events(**_) -> None:\n"
        "    # Validate silver.user_events: count > 0, event_type not null.\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "\n"
        "    client = Client(CH_HOST)\n"
        "    passed = True\n"
        "\n"
        '    count = client.execute("SELECT count() FROM silver.user_events")[0][0]\n'
        "    if count == 0:\n"
        '        log.error("ge_user_events: silver.user_events is empty")\n'
        "        passed = False\n"
        "    else:\n"
        '        log.info("ge_user_events: silver.user_events row count = %d", count)\n'
        "\n"
        "    null_event_types = client.execute(\n"
        "        \"SELECT count() FROM silver.user_events WHERE event_type IS NULL OR event_type = ''\"\n"
        "    )[0][0]\n"
        "    if null_event_types > 0:\n"
        '        log.error("ge_user_events: %d rows have null/empty event_type", null_event_types)\n'
        "        passed = False\n"
        "    else:\n"
        '        log.info("ge_user_events: event_type null check passed")\n'
        "\n"
        '    _CHECK_RESULTS["ge_user_events"] = passed\n'
        "    if not passed:\n"
        '        raise ValueError("ge_user_events: one or more quality checks failed -- see logs")\n'
        "\n"
        "\n"
        "def _quality_gate(**_) -> bool:\n"
        "    # Short-circuit: return True only when all upstream checks passed.\n"
        "    all_passed = all(_CHECK_RESULTS.values())\n"
        "    if not all_passed:\n"
        '        log.error("quality_gate: FAILED -- results: %s", _CHECK_RESULTS)\n'
        "    else:\n"
        '        log.info("quality_gate: all checks passed")\n'
        "    return all_passed\n"
        "\n"
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_quality_gate",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@daily",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "quality", "ge"],\n'
        ") as dag:\n"
        "\n"
        "    ge_orders = PythonOperator(\n"
        '        task_id="ge_orders",\n'
        "        python_callable=_check_orders,\n"
        "    )\n"
        "\n"
        "    ge_user_events = PythonOperator(\n"
        '        task_id="ge_user_events",\n'
        "        python_callable=_check_user_events,\n"
        "    )\n"
        "\n"
        "    quality_gate = ShortCircuitOperator(\n"
        '        task_id="quality_gate",\n'
        "        python_callable=_quality_gate,\n"
        '        trigger_rule="all_done",\n'
        "    )\n"
        "\n"
        "    [ge_orders, ge_user_events] >> quality_gate\n"
    )
