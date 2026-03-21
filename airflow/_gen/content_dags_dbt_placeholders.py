"""DAG content: DAG 2 (dbt ClickHouse), DAG 2b (staging), DAG 3 (placeholder), DAG 4 (placeholder)."""

_DBT_DIR = "/opt/airflow/dbt/orderflow_clickhouse"


def dag_dbt_clickhouse() -> str:
    return (
        "# airflow/dags/orderflow_dbt_clickhouse.py\n"
        "# Phase 6 -- DAG 2: Daily dbt run against ClickHouse (dev target).\n"
        "# Runs dbt run -> dbt snapshot -> dbt test in sequence.\n"
        "from __future__ import annotations\n"
        "\n"
        "from datetime import datetime, timedelta\n"
        "\n"
        "from airflow import DAG\n"
        "from airflow.operators.bash import BashOperator\n"
        "\n"
        "DEFAULT_ARGS = {\n"
        '    "owner": "orderflow",\n'
        '    "retries": 1,\n'
        '    "retry_delay": timedelta(minutes=5),\n'
        "}\n"
        "\n"
        f'DBT_DIR = "{_DBT_DIR}"\n'
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_dbt_clickhouse",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@daily",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "dbt", "clickhouse"],\n'
        ") as dag:\n"
        "\n"
        "    dbt_run_dev = BashOperator(\n"
        '        task_id="dbt_run_dev",\n'
        '        bash_command=f"cd {DBT_DIR} && dbt run --profiles-dir . --no-version-check",\n'
        "    )\n"
        "\n"
        "    dbt_snapshot = BashOperator(\n"
        '        task_id="dbt_snapshot",\n'
        '        bash_command=f"cd {DBT_DIR} && dbt snapshot --profiles-dir . --no-version-check",\n'
        "    )\n"
        "\n"
        "    dbt_test = BashOperator(\n"
        '        task_id="dbt_test",\n'
        '        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir . --no-version-check",\n'
        "    )\n"
        "\n"
        "    dbt_run_dev >> dbt_snapshot >> dbt_test\n"
    )


def dag_dbt_clickhouse_staging() -> str:
    return (
        "# airflow/dags/orderflow_dbt_clickhouse_staging.py\n"
        "# Phase 6 -- DAG 2b: Manual-trigger dbt run against ClickHouse staging target.\n"
        "# Targets dbt_staging__gold database. schedule=None means manual trigger only.\n"
        "from __future__ import annotations\n"
        "\n"
        "from datetime import datetime, timedelta\n"
        "\n"
        "from airflow import DAG\n"
        "from airflow.operators.bash import BashOperator\n"
        "\n"
        "DEFAULT_ARGS = {\n"
        '    "owner": "orderflow",\n'
        '    "retries": 1,\n'
        '    "retry_delay": timedelta(minutes=5),\n'
        "}\n"
        "\n"
        f'DBT_DIR = "{_DBT_DIR}"\n'
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_dbt_clickhouse_staging",\n'
        "    default_args=DEFAULT_ARGS,\n"
        "    schedule_interval=None,\n"
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "dbt", "clickhouse", "staging"],\n'
        ") as dag:\n"
        "\n"
        "    dbt_run_staging = BashOperator(\n"
        '        task_id="dbt_run_staging",\n'
        "        bash_command=(\n"
        '            f"cd {DBT_DIR} && dbt run --profiles-dir . --target staging --no-version-check"\n'
        "        ),\n"
        "    )\n"
    )


def dag_dbt_spark() -> str:
    return (
        "# airflow/dags/orderflow_dbt_spark.py\n"
        "# Phase 6 -- DAG 3: dbt-spark pipeline.\n"
        "# SKIPPED: dbt-spark is not available in this deployment (platform limitation).\n"
        "# This DAG is a no-op placeholder that logs the skip reason.\n"
        "from __future__ import annotations\n"
        "\n"
        "import logging\n"
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
        "\n"
        "def _placeholder(**_) -> None:\n"
        "    log.info(\n"
        '        "DAG 3 (orderflow_dbt_spark): dbt-spark SKIPPED -- "\n'
        '        "platform limitation: dbt-spark not installed in this Airflow image."\n'
        "    )\n"
        "\n"
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_dbt_spark",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@daily",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "dbt", "spark", "skipped"],\n'
        ") as dag:\n"
        "\n"
        "    placeholder = PythonOperator(\n"
        '        task_id="placeholder",\n'
        "        python_callable=_placeholder,\n"
        "    )\n"
    )


def dag_delta_optimize() -> str:
    return (
        "# airflow/dags/orderflow_delta_optimize.py\n"
        "# Phase 6 -- DAG 4: Delta Lake OPTIMIZE / VACUUM jobs.\n"
        "# SKIPPED: Delta OPTIMIZE requires in-process Spark with S3A auth which is\n"
        "# unavailable in the Kind cluster environment (auth issue with MinIO via S3A).\n"
        "from __future__ import annotations\n"
        "\n"
        "import logging\n"
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
        "\n"
        "def _placeholder(**_) -> None:\n"
        "    log.info(\n"
        '        "DAG 4 (orderflow_delta_optimize): Delta OPTIMIZE SKIPPED -- "\n'
        '        "S3A auth limitation on Kind cluster prevents in-process Spark access to MinIO."\n'
        "    )\n"
        "\n"
        "\n"
        "with DAG(\n"
        '    dag_id="orderflow_delta_optimize",\n'
        "    default_args=DEFAULT_ARGS,\n"
        '    schedule_interval="@weekly",\n'
        "    start_date=datetime(2024, 1, 1),\n"
        "    catchup=False,\n"
        '    tags=["phase6", "delta", "optimize", "skipped"],\n'
        ") as dag:\n"
        "\n"
        "    placeholder = PythonOperator(\n"
        '        task_id="placeholder",\n'
        "        python_callable=_placeholder,\n"
        "    )\n"
    )
