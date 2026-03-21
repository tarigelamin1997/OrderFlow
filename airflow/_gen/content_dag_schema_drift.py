"""DAG content: DAG 6 -- orderflow_schema_drift (@daily)."""

_CH_HOST = "clickhouse.clickhouse.svc.cluster.local"
_SNAPSHOT_DIR = "/opt/airflow/schema_snapshots"


def dag_schema_drift() -> str:
    return (
        "# airflow/dags/orderflow_schema_drift.py\n"
        "# Phase 6 -- DAG 6: Daily schema drift detection for silver.* tables.\n"
        "# Compares live DESCRIBE output against expected snapshots stored as JSON files\n"
        "# at /opt/airflow/schema_snapshots/{entity}_schema.json.\n"
        "from __future__ import annotations\n"
        "\n"
        "import json\n"
        "import logging\n"
        "import os\n"
        "from datetime import datetime, timedelta\n"
        "\n"
        "from airflow import DAG\n"
        "from airflow.operators.python import PythonOperator\n"
        "\n"
        "log = logging.getLogger(__name__)\n"
        "\n"
        "DEFAULT_ARGS = {\n"
        '    "owner": "orderflow",\n'
        '    "retries": 1,\n'
        '    "retry_delay": timedelta(minutes=5),\n'
        "}\n"
        "\n"
        f'CH_HOST = "{_CH_HOST}"\n'
        f'SNAPSHOT_DIR = "{_SNAPSHOT_DIR}"\n'
        "\n"
        "SILVER_TABLES = [\n"
        '    "orders",\n'
        '    "users",\n'
        '    "restaurants",\n'
        '    "drivers",\n'
        '    "user_events",\n'
        '    "delivery_updates",\n'
        "]\n"
        "\n"
        "\n"
        "def _load_snapshot(entity: str) -> list:\n"
        "    # Load expected schema from JSON snapshot file.\n"
        "    path = os.path.join(SNAPSHOT_DIR, f\"{entity}_schema.json\")\n"
        "    if not os.path.exists(path):\n"
        '        log.warning("Schema snapshot not found: %s", path)\n'
        "        return []\n"
        '    with open(path, encoding="utf-8") as fh:\n'
        "        data = json.load(fh)\n"
        '    return data.get("columns", [])\n'
        "\n"
        "\n"
        "def _get_live_schema(client, table: str) -> list:\n"
        "    # Fetch live column names and types from ClickHouse DESCRIBE.\n"
        "    rows = client.execute(f\"DESCRIBE TABLE silver.{table}\")\n"
        '    return [{"name": row[0], "type": row[1]} for row in rows]\n'
        "\n"
        "\n"
        "def _check_silver_schema(**_) -> dict:\n"
        "    # Compare each silver table's live schema against expected snapshot.\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "\n"
        "    client = Client(CH_HOST)\n"
        "    drift_found = False\n"
        "\n"
        "    for table in SILVER_TABLES:\n"
        "        expected = _load_snapshot(table)\n"
        "        if not expected:\n"
        '            log.info("Skipping %s: no snapshot file", table)\n'
        "            continue\n"
        "        live = _get_live_schema(client, table)\n"
        '        expected_map = {col["name"]: col["type"] for col in expected}\n'
        '        live_map = {col["name"]: col["type"] for col in live}\n'
        "        added = set(live_map) - set(expected_map)\n"
        "        removed = set(expected_map) - set(live_map)\n"
        "        type_changes = {\n"
        "            col: (expected_map[col], live_map[col])\n"
        "            for col in set(expected_map) & set(live_map)\n"
        "            if expected_map[col] != live_map[col]\n"
        "        }\n"
        "        if added or removed or type_changes:\n"
        "            drift_found = True\n"
        "            log.warning(\n"
        '                "Schema drift in silver.%s: added=%s removed=%s type_changes=%s",\n'
        "                table, sorted(added), sorted(removed), type_changes,\n"
        "            )\n"
        "        else:\n"
        '            log.info("silver.%s: schema matches snapshot", table)\n'
        "\n"
        "    if drift_found:\n"
        '        log.error("Schema drift detected -- downstream alert_on_drift will log details")\n'
        "    else:\n"
        '        log.info("No schema drift detected in silver.* tables")\n'
        '    return {"drift_found": drift_found}\n'
        "\n"
        "\n"
        "def _alert_on_drift(**context) -> None:\n"
        "    # Log any drift found by check_silver_schema; write to gold.schema_drift_log.\n"
        "    ti = context[\"ti\"]\n"
        '    result = ti.xcom_pull(task_ids="check_silver_schema") or {}\n'
        '    drift_found = result.get("drift_found", False)\n'
        "    if not drift_found:\n"
        '        log.info("alert_on_drift: no drift to report")\n'
        "        return\n"
        '    log.warning("alert_on_drift: schema drift detected -- see check_silver_schema logs")\n'
        "    try:\n"
        "        from clickhouse_driver import Client  # noqa: PLC0415\n"
        "        client = Client(CH_HOST)\n"
        '        dag_id = context["dag"].dag_id\n'
        '        run_id = context["run_id"]\n'
        "        client.execute(\n"
        '            "INSERT INTO gold.schema_drift_log "\n'
        '            "(dag_id, run_id, drift_detected, checked_at) "\n'
        '            "VALUES (%(dag_id)s, %(run_id)s, %(drift)s, now())",\n'
        '            {"dag_id": dag_id, "run_id": run_id, "drift": 1},\n'
        "        )\n"
        "    except Exception as exc:  # noqa: BLE001\n"
        '        log.warning("alert_on_drift: could not write to schema_drift_log: %s", exc)\n'
        "\n"
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_schema_drift",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@daily",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "schema", "drift"],\n'
        ") as dag:\n"
        "\n"
        "    check_silver_schema = PythonOperator(\n"
        '        task_id="check_silver_schema",\n'
        "        python_callable=_check_silver_schema,\n"
        "    )\n"
        "\n"
        "    alert_on_drift = PythonOperator(\n"
        '        task_id="alert_on_drift",\n'
        "        python_callable=_alert_on_drift,\n"
        "    )\n"
        "\n"
        "    check_silver_schema >> alert_on_drift\n"
    )
