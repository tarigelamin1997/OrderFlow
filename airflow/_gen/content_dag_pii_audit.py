"""DAG content: DAG 7 -- orderflow_pii_audit (@weekly)."""

_CH_HOST = "clickhouse.clickhouse.svc.cluster.local"


def dag_pii_audit() -> str:
    return (
        "# airflow/dags/orderflow_pii_audit.py\n"
        "# Phase 6 -- DAG 7: Weekly PII audit across silver and bronze layers.\n"
        "# Checks that PII fields are properly hashed/removed.\n"
        "# All three audit tasks run in parallel. Failures logged to gold.pii_audit_log.\n"
        "from __future__ import annotations\n"
        "\n"
        "import logging\n"
        "import re\n"
        "from datetime import datetime, timedelta\n"
        "from typing import Any\n"
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
        'SHA256_RE = re.compile(r"^[a-f0-9]{64}$")\n'
        'HASH_RE = re.compile(r"^[a-f0-9]{16,}$")\n'
        "\n"
        "\n"
        "def _write_audit_log(\n"
        "    client: Any, dag_id: str, task_id: str, entity: str, layer: str,\n"
        "    check_type: str, passed: bool, sample_count: int,\n"
        "    failure_count: int, failure_detail: str,\n"
        ") -> None:\n"
        "    # Insert a row into gold.pii_audit_log.\n"
        "    try:\n"
        "        client.execute(\n"
        '            "INSERT INTO gold.pii_audit_log "\n'
        '            "(dag_id, task_id, entity, layer, check_type, passed, "\n'
        '            "sample_count, failure_count, failure_detail) "\n'
        '            "VALUES (%(dag_id)s, %(task_id)s, %(entity)s, %(layer)s, %(check_type)s, "\n'
        '            "%(passed)s, %(sample_count)s, %(failure_count)s, %(failure_detail)s)",\n'
        "            {\n"
        '                "dag_id": dag_id, "task_id": task_id, "entity": entity,\n'
        '                "layer": layer, "check_type": check_type,\n'
        '                "passed": 1 if passed else 0, "sample_count": sample_count,\n'
        '                "failure_count": failure_count, "failure_detail": failure_detail,\n'
        "            },\n"
        "        )\n"
        "    except Exception as exc:  # noqa: BLE001\n"
        '        log.warning("Could not write to pii_audit_log: %s", exc)\n'
        "\n"
        "\n"
        "def _audit_silver_users(**context) -> None:\n"
        "    # Check that silver.users.email_hash matches SHA-256 hex pattern.\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "    client = Client(CH_HOST)\n"
        '    dag_id = context["dag"].dag_id\n'
        '    rows = client.execute("SELECT email_hash FROM silver.users LIMIT 10000")\n'
        "    sample_count = len(rows)\n"
        '    failures = [r[0] for r in rows if not SHA256_RE.match(str(r[0] or ""))]\n'
        "    failure_count = len(failures)\n"
        "    passed = failure_count == 0\n"
        '    detail = "" if passed else f"sample failures: {failures[:5]}"\n'
        '    log.info("audit_silver_users: sample=%d failures=%d passed=%s", sample_count, failure_count, passed)\n'
        '    _write_audit_log(client, dag_id, "audit_silver_users", "users", "silver",\n'
        '        "email_hash_sha256", passed, sample_count, failure_count, detail)\n'
        "    if not passed:\n"
        '        raise ValueError(f"audit_silver_users: {failure_count} email_hash values fail SHA-256 pattern")\n'
        "\n"
        "\n"
        "def _audit_silver_drivers(**context) -> None:\n"
        "    # Check that silver.drivers.phone_hash matches a hex hash pattern.\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "    client = Client(CH_HOST)\n"
        '    dag_id = context["dag"].dag_id\n'
        '    rows = client.execute("SELECT phone_hash FROM silver.drivers LIMIT 10000")\n'
        "    sample_count = len(rows)\n"
        '    failures = [r[0] for r in rows if not HASH_RE.match(str(r[0] or ""))]\n'
        "    failure_count = len(failures)\n"
        "    passed = failure_count == 0\n"
        '    detail = "" if passed else f"sample failures: {failures[:5]}"\n'
        '    log.info("audit_silver_drivers: sample=%d failures=%d passed=%s", sample_count, failure_count, passed)\n'
        '    _write_audit_log(client, dag_id, "audit_silver_drivers", "drivers", "silver",\n'
        '        "phone_hash_hex", passed, sample_count, failure_count, detail)\n'
        "    if not passed:\n"
        '        raise ValueError(f"audit_silver_drivers: {failure_count} phone_hash values fail hex pattern")\n'
        "\n"
        "\n"
        "def _audit_bronze_spot(**context) -> None:\n"
        "    # Spot-check that bronze.users_raw.after_email has no raw emails (no '@').\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "    client = Client(CH_HOST)\n"
        '    dag_id = context["dag"].dag_id\n'
        "    rows = client.execute(\n"
        "        \"SELECT count() FROM bronze.users_raw WHERE after_email LIKE '%@%' LIMIT 1\"\n"
        "    )\n"
        "    leak_count = rows[0][0] if rows else 0\n"
        "    sc_rows = client.execute(\"SELECT count() FROM bronze.users_raw\")\n"
        "    sample_count = sc_rows[0][0] if sc_rows else 0\n"
        "    passed = leak_count == 0\n"
        '    detail = "" if passed else f"raw email leak count: {leak_count}"\n'
        '    log.info("audit_bronze_spot: sample=%d email_leaks=%d passed=%s", sample_count, leak_count, passed)\n'
        '    _write_audit_log(client, dag_id, "audit_bronze_spot", "users_raw", "bronze",\n'
        '        "no_raw_email_in_after_email", passed, sample_count, int(leak_count), detail)\n'
        "    if not passed:\n"
        '        raise ValueError(f"audit_bronze_spot: {leak_count} rows expose raw email in after_email")\n'
        "\n"
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_pii_audit",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@weekly",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "pii", "audit", "compliance"],\n'
        ") as dag:\n"
        "\n"
        "    audit_silver_users = PythonOperator(\n"
        '        task_id="audit_silver_users",\n'
        "        python_callable=_audit_silver_users,\n"
        "    )\n"
        "\n"
        "    audit_silver_drivers = PythonOperator(\n"
        '        task_id="audit_silver_drivers",\n'
        "        python_callable=_audit_silver_drivers,\n"
        "    )\n"
        "\n"
        "    audit_bronze_spot = PythonOperator(\n"
        '        task_id="audit_bronze_spot",\n'
        "        python_callable=_audit_bronze_spot,\n"
        "    )\n"
        "\n"
        "    # All three tasks run in parallel (no dependencies between them).\n"
        "    [audit_silver_users, audit_silver_drivers, audit_bronze_spot]\n"
    )
