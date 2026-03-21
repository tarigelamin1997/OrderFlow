"""DAG content: DAG 1 -- orderflow_batch_ingestion (@hourly)."""


def dag_batch_ingestion() -> str:
    return (
        "# airflow/dags/orderflow_batch_ingestion.py\n"
        "# Phase 6 -- DAG 1: Hourly batch ingestion pipeline.\n"
        "# Triggers SparkApplications in the 'default' namespace for silver -> gold layers.\n"
        "from __future__ import annotations\n"
        "\n"
        "import logging\n"
        "from datetime import datetime, timedelta\n"
        "\n"
        "from airflow import DAG\n"
        "from airflow.operators.bash import BashOperator\n"
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
        'SPARK_NS = "default"\n'
        "\n"
        "\n"
        "def _spark_cmd(name: str, manifest: str) -> str:\n"
        "    # Return bash command: delete existing SparkApp, apply manifest, wait for Completed.\n"
        "    return (\n"
        '        f"kubectl delete sparkapplication {name} -n {SPARK_NS} --ignore-not-found && "\n'
        '        f"kubectl apply -f /opt/airflow/spark-manifests/{manifest} && "\n'
        '        f"kubectl wait --for=condition=Completed sparkapplication/{name} "\n'
        '        f"-n {SPARK_NS} --timeout=600s"\n'
        "    )\n"
        "\n"
        "\n"
        "def _check_new_parquet(**_) -> bool:\n"
        "    # Return True when bronze.orders_raw has at least one row (proxy for new data).\n"
        "    from clickhouse_driver import Client  # noqa: PLC0415\n"
        "\n"
        '    client = Client("clickhouse.clickhouse.svc.cluster.local")\n'
        '    result = client.execute("SELECT count() FROM bronze.orders_raw")\n'
        "    row_count = result[0][0] if result else 0\n"
        '    log.info("bronze.orders_raw row count: %d", row_count)\n'
        "    return row_count > 0\n"
        "\n"
        "\n"
        "def _mark_batch_complete(**context) -> None:\n"
        "    # Log a record to gold.dag_run_log (no-op if table not yet available).\n"
        "    try:\n"
        "        from clickhouse_driver import Client  # noqa: PLC0415\n"
        "\n"
        '        client = Client("clickhouse.clickhouse.svc.cluster.local")\n'
        '        dag_id = context["dag"].dag_id\n'
        '        run_id = context["run_id"]\n'
        "        client.execute(\n"
        '            "INSERT INTO gold.dag_run_log (dag_id, run_id, status, completed_at) "\n'
        '            "VALUES (%(dag_id)s, %(run_id)s, %(status)s, now())",\n'
        '            {"dag_id": dag_id, "run_id": run_id, "status": "success"},\n'
        "        )\n"
        '        log.info("Logged batch completion for run_id=%s", run_id)\n'
        "    except Exception as exc:  # noqa: BLE001\n"
        '        log.warning("mark_batch_complete: could not write to dag_run_log: %s", exc)\n'
        "\n"
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_batch_ingestion",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@hourly",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "batch", "spark"],\n'
        ") as dag:\n"
        "\n"
        "    check_new_parquet = ShortCircuitOperator(\n"
        '        task_id="check_new_parquet",\n'
        "        python_callable=_check_new_parquet,\n"
        "    )\n"
        "\n"
        "    run_silver_ingestion = BashOperator(\n"
        '        task_id="run_silver_ingestion",\n'
        '        bash_command=_spark_cmd("silver-ingestion", "silver-ingestion.yaml"),\n'
        "    )\n"
        "\n"
        "    run_feature_engineering = BashOperator(\n"
        '        task_id="run_feature_engineering",\n'
        '        bash_command=_spark_cmd("feature-engineering", "feature-engineering.yaml"),\n'
        "    )\n"
        "\n"
        "    run_gold_writer = BashOperator(\n"
        '        task_id="run_gold_writer",\n'
        '        bash_command=_spark_cmd("gold-writer", "gold-writer.yaml"),\n'
        "    )\n"
        "\n"
        "    mark_batch_complete = PythonOperator(\n"
        '        task_id="mark_batch_complete",\n'
        "        python_callable=_mark_batch_complete,\n"
        "    )\n"
        "\n"
        "    (\n"
        "        check_new_parquet\n"
        "        >> run_silver_ingestion\n"
        "        >> run_feature_engineering\n"
        "        >> run_gold_writer\n"
        "        >> mark_batch_complete\n"
        "    )\n"
    )
