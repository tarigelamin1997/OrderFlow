#!/usr/bin/env python3
"""
gen_phase6.py -- Phase 6 file generator for OrderFlow.

Copy this file (and the whole airflow/_gen/ directory) to the EC2 instance
inside ~/OrderFlow, then run:

    python3 ~/OrderFlow/gen_phase6.py

All Phase 6 files will be created under ~/OrderFlow/.
Content modules live in airflow/_gen/ alongside the generator.

Files created (16 total):
  airflow/dags/orderflow_batch_ingestion.py          DAG 1  (@hourly)
  airflow/dags/orderflow_dbt_clickhouse.py           DAG 2  (@daily)
  airflow/dags/orderflow_dbt_clickhouse_staging.py   DAG 2b (manual)
  airflow/dags/orderflow_dbt_spark.py                DAG 3  (@daily, no-op placeholder)
  airflow/dags/orderflow_delta_optimize.py           DAG 4  (@weekly, no-op placeholder)
  airflow/dags/orderflow_quality_gate.py             DAG 5  (@daily)
  airflow/dags/orderflow_schema_drift.py             DAG 6  (@daily)
  airflow/dags/orderflow_pii_audit.py                DAG 7  (@weekly)
  airflow/schema_snapshots/orders_schema.json
  airflow/schema_snapshots/users_schema.json
  airflow/schema_snapshots/restaurants_schema.json
  airflow/schema_snapshots/drivers_schema.json
  airflow/schema_snapshots/user_events_schema.json
  airflow/schema_snapshots/delivery_updates_schema.json
  clickhouse/gold/12_pii_audit_log.sql
  scripts/verify_phase6.sh

Deviations from plan incorporated:
  - dbt-spark SKIPPED: DAG 3 is a no-op placeholder (logs skip reason)
  - Delta OPTIMIZE SKIPPED: DAG 4 is a no-op placeholder (S3A auth issue on Kind)
  - SparkApplication namespace is 'default', NOT 'spark'
  - Mart tables use MergeTree (not SummingMergeTree)
"""

import os
import stat
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "airflow", "_gen"))

from content_dag_batch_ingestion import dag_batch_ingestion   # noqa: E402
from content_dag_quality_gate import dag_quality_gate         # noqa: E402
from content_dags_dbt_placeholders import (                   # noqa: E402
    dag_dbt_clickhouse,
    dag_dbt_clickhouse_staging,
    dag_dbt_spark,
    dag_delta_optimize,
)
from content_dag_schema_drift import dag_schema_drift         # noqa: E402
from content_dag_pii_audit import dag_pii_audit               # noqa: E402
from content_schemas import (                                  # noqa: E402
    schema_orders,
    schema_users,
    schema_restaurants,
    schema_drivers,
    schema_user_events,
    schema_delivery_updates,
)
from content_pii_audit_ddl import pii_audit_log_sql           # noqa: E402
from content_verify_phase6 import verify_phase6_sh            # noqa: E402

BASE = os.path.expanduser("~/OrderFlow")

# (relative_path, content_callable, executable_flag)
FILES = [
    # --- DAGs ----------------------------------------------------------------
    (
        "airflow/dags/orderflow_batch_ingestion.py",
        dag_batch_ingestion,
        False,
    ),
    (
        "airflow/dags/orderflow_dbt_clickhouse.py",
        dag_dbt_clickhouse,
        False,
    ),
    (
        "airflow/dags/orderflow_dbt_clickhouse_staging.py",
        dag_dbt_clickhouse_staging,
        False,
    ),
    (
        "airflow/dags/orderflow_dbt_spark.py",
        dag_dbt_spark,
        False,
    ),
    (
        "airflow/dags/orderflow_delta_optimize.py",
        dag_delta_optimize,
        False,
    ),
    (
        "airflow/dags/orderflow_quality_gate.py",
        dag_quality_gate,
        False,
    ),
    (
        "airflow/dags/orderflow_schema_drift.py",
        dag_schema_drift,
        False,
    ),
    (
        "airflow/dags/orderflow_pii_audit.py",
        dag_pii_audit,
        False,
    ),
    # --- Schema snapshots ----------------------------------------------------
    (
        "airflow/schema_snapshots/orders_schema.json",
        schema_orders,
        False,
    ),
    (
        "airflow/schema_snapshots/users_schema.json",
        schema_users,
        False,
    ),
    (
        "airflow/schema_snapshots/restaurants_schema.json",
        schema_restaurants,
        False,
    ),
    (
        "airflow/schema_snapshots/drivers_schema.json",
        schema_drivers,
        False,
    ),
    (
        "airflow/schema_snapshots/user_events_schema.json",
        schema_user_events,
        False,
    ),
    (
        "airflow/schema_snapshots/delivery_updates_schema.json",
        schema_delivery_updates,
        False,
    ),
    # --- ClickHouse DDL ------------------------------------------------------
    (
        "clickhouse/gold/12_pii_audit_log.sql",
        pii_audit_log_sql,
        False,
    ),
    # --- Verify script -------------------------------------------------------
    (
        "scripts/verify_phase6.sh",
        verify_phase6_sh,
        True,
    ),
]


def main() -> None:
    print(f"Writing {len(FILES)} Phase 6 files under {BASE}/")
    print()
    for rel_path, content_fn, executable in FILES:
        abs_path = os.path.join(BASE, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content_fn())
        if executable:
            mode = os.stat(abs_path).st_mode
            os.chmod(abs_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  created (chmod +x): {rel_path}")
        else:
            print(f"  created:            {rel_path}")

    print()
    print(f"Done. {len(FILES)} files written.")
    print()
    print("Next steps (from ~/OrderFlow):")
    print()
    print("  1. Apply ClickHouse DDL:")
    print("     clickhouse-client --host localhost --port 30900 \\")
    print("       --query \"$(cat clickhouse/gold/12_pii_audit_log.sql)\"")
    print()
    print("  2. Copy DAGs and schema snapshots into Airflow pod:")
    print("     kubectl cp airflow/dags/ airflow/airflow-0:/opt/airflow/dags/ -n airflow")
    print("     kubectl cp airflow/schema_snapshots/ \\")
    print("       airflow/airflow-0:/opt/airflow/schema_snapshots/ -n airflow")
    print()
    print("  3. Copy dbt project into Airflow pod (if not already present):")
    print("     kubectl cp dbt/orderflow_clickhouse/ \\")
    print("       airflow/airflow-0:/opt/airflow/dbt/orderflow_clickhouse/ -n airflow")
    print()
    print("  4. Restart Airflow scheduler to pick up new DAGs:")
    print("     kubectl rollout restart statefulset/airflow -n airflow")
    print()
    print("  5. Trigger DAG 2b to create dbt_staging__gold database:")
    print("     curl -X POST -u admin:admin \\")
    print("       http://localhost:30080/api/v1/dags/orderflow_dbt_clickhouse_staging/dagRuns \\")
    print("       -H 'Content-Type: application/json' -d '{\"conf\":{}}'")
    print()
    print("  6. Run verification:")
    print("     bash ~/OrderFlow/scripts/verify_phase6.sh")


if __name__ == "__main__":
    main()
