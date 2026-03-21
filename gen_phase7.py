#!/usr/bin/env python3
"""
gen_phase7.py -- Phase 7 file generator for OrderFlow.

Copy this file AND the observability/_gen/ directory to the EC2 instance
inside ~/OrderFlow, then run:

    python3 ~/OrderFlow/gen_phase7.py

All Phase 7 files will be created under ~/OrderFlow/.
Content modules live in observability/_gen/ alongside the generator.

Files created (~20 total):
  clickhouse/gold/13_dag_run_log.sql
  clickhouse/gold/14_schema_drift_log.sql
  observability/plugins/dag_telemetry_listener.py
  observability/grafana/provisioning/dashboards/orderflow.yaml
  observability/grafana/provisioning/alerting/orderflow-alerts.yaml
  observability/grafana/dashboards/pipeline_health.json
  observability/grafana/dashboards/data_quality.json
  observability/grafana/dashboards/clickhouse_ops.json
  observability/grafana/dashboards/business_metrics.json
  observability/grafana/dashboards/finops_resources.json
  observability/grafana/k8s/grafana-dashboard-configmap.yaml
  observability/grafana/k8s/grafana-volume-patch.yaml
  observability/openlineage/openlineage.yml
  observability/openlineage/k8s/airflow-openlineage-patch.yaml
  observability/k8s/plugins-configmap.yaml
  scripts/verify_phase7.sh

Environment facts baked in:
  - Grafana datasource UID: PDEE91DDB90597936
  - Grafana type: vertamedia-clickhouse-datasource
  - Grafana admin password: orderflow
  - Grafana: deployment 'grafana' in monitoring namespace
  - Marquez: marquez-api.marquez.svc.cluster.local:5000
  - ClickHouse plugin host: clickhouse.clickhouse.svc.cluster.local (port 9000)
  - Airflow: statefulset 'airflow' in airflow namespace (NOT a Deployment)
  - Dashboard 4 queries dbt_dev__gold (NOT dbt_staging__gold)
"""

import os
import stat
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "observability", "_gen"))

from content_ch_ddl import dag_run_log_sql, schema_drift_log_sql          # noqa: E402
from content_telemetry_plugin import dag_telemetry_listener                # noqa: E402
from content_grafana_provisioning import (                                  # noqa: E402
    grafana_dashboards_provisioning_yaml,
    grafana_alerts_yaml,
)
from content_dashboards import (                                            # noqa: E402
    pipeline_health_json,
    data_quality_json,
    clickhouse_ops_json,
    business_metrics_json,
    finops_resources_json,
)
from content_k8s_patches import (                                           # noqa: E402
    grafana_dashboard_configmap_yaml,
    grafana_volume_patch_yaml,
    airflow_openlineage_patch_yaml,
    plugins_configmap_yaml,
    openlineage_yml,
)
from content_verify_phase7 import verify_phase7_sh                         # noqa: E402

BASE = os.path.expanduser("~/OrderFlow")

# (relative_path, content_callable, executable_flag)
FILES = [
    # --- ClickHouse DDL ------------------------------------------------------
    (
        "clickhouse/gold/13_dag_run_log.sql",
        dag_run_log_sql,
        False,
    ),
    (
        "clickhouse/gold/14_schema_drift_log.sql",
        schema_drift_log_sql,
        False,
    ),
    # --- Airflow telemetry plugin --------------------------------------------
    (
        "observability/plugins/dag_telemetry_listener.py",
        dag_telemetry_listener,
        False,
    ),
    # --- Grafana provisioning ------------------------------------------------
    (
        "observability/grafana/provisioning/dashboards/orderflow.yaml",
        grafana_dashboards_provisioning_yaml,
        False,
    ),
    (
        "observability/grafana/provisioning/alerting/orderflow-alerts.yaml",
        grafana_alerts_yaml,
        False,
    ),
    # --- Grafana dashboards --------------------------------------------------
    (
        "observability/grafana/dashboards/pipeline_health.json",
        pipeline_health_json,
        False,
    ),
    (
        "observability/grafana/dashboards/data_quality.json",
        data_quality_json,
        False,
    ),
    (
        "observability/grafana/dashboards/clickhouse_ops.json",
        clickhouse_ops_json,
        False,
    ),
    (
        "observability/grafana/dashboards/business_metrics.json",
        business_metrics_json,
        False,
    ),
    (
        "observability/grafana/dashboards/finops_resources.json",
        finops_resources_json,
        False,
    ),
    # --- Grafana K8s manifests -----------------------------------------------
    (
        "observability/grafana/k8s/grafana-dashboard-configmap.yaml",
        grafana_dashboard_configmap_yaml,
        False,
    ),
    (
        "observability/grafana/k8s/grafana-volume-patch.yaml",
        grafana_volume_patch_yaml,
        False,
    ),
    # --- OpenLineage ---------------------------------------------------------
    (
        "observability/openlineage/openlineage.yml",
        openlineage_yml,
        False,
    ),
    (
        "observability/openlineage/k8s/airflow-openlineage-patch.yaml",
        airflow_openlineage_patch_yaml,
        False,
    ),
    # --- K8s reference manifests ---------------------------------------------
    (
        "observability/k8s/plugins-configmap.yaml",
        plugins_configmap_yaml,
        False,
    ),
    # --- Verify script -------------------------------------------------------
    (
        "scripts/verify_phase7.sh",
        verify_phase7_sh,
        True,
    ),
]


def main() -> None:
    print(f"Writing {len(FILES)} Phase 7 files under {BASE}/")
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
    print("Apply Sequence (from ~/OrderFlow):")
    print()
    print("  Step 1 -- Apply ClickHouse DDL for dag_run_log:")
    print("    clickhouse-client --host localhost --port 30900 \\")
    print("      --query \"$(cat clickhouse/gold/13_dag_run_log.sql)\"")
    print()
    print("  Step 2 -- Apply ClickHouse DDL for schema_drift_log:")
    print("    clickhouse-client --host localhost --port 30900 \\")
    print("      --query \"$(cat clickhouse/gold/14_schema_drift_log.sql)\"")
    print()
    print("  Step 3 -- Create airflow-plugins ConfigMap:")
    print("    kubectl create configmap airflow-plugins \\")
    print("      --from-file=dag_telemetry_listener.py=observability/plugins/dag_telemetry_listener.py \\")
    print("      -n airflow")
    print()
    print("  Step 4 -- Patch Airflow StatefulSet (OpenLineage + plugins volume):")
    print("    kubectl patch statefulset airflow -n airflow \\")
    print("      --patch-file observability/openlineage/k8s/airflow-openlineage-patch.yaml")
    print()
    print("  Step 5 -- Restart Airflow to load the plugin:")
    print("    kubectl rollout restart statefulset/airflow -n airflow")
    print("    kubectl rollout status statefulset/airflow -n airflow --timeout=300s")
    print()
    print("  Step 6 -- Create Grafana dashboard ConfigMaps:")
    print("    kubectl create configmap grafana-dashboards-json \\")
    print("      --from-file=pipeline_health.json=observability/grafana/dashboards/pipeline_health.json \\")
    print("      --from-file=data_quality.json=observability/grafana/dashboards/data_quality.json \\")
    print("      --from-file=clickhouse_ops.json=observability/grafana/dashboards/clickhouse_ops.json \\")
    print("      --from-file=business_metrics.json=observability/grafana/dashboards/business_metrics.json \\")
    print("      --from-file=finops_resources.json=observability/grafana/dashboards/finops_resources.json \\")
    print("      -n monitoring")
    print()
    print("  Step 7 -- Create Grafana provisioning ConfigMaps:")
    print("    kubectl create configmap grafana-dashboards-provisioning \\")
    print("      --from-file=orderflow.yaml=observability/grafana/provisioning/dashboards/orderflow.yaml \\")
    print("      -n monitoring")
    print("    kubectl create configmap grafana-alerting-provisioning \\")
    print("      --from-file=orderflow-alerts.yaml=observability/grafana/provisioning/alerting/orderflow-alerts.yaml \\")
    print("      -n monitoring")
    print()
    print("  Step 8 -- Patch Grafana Deployment (volumes for dashboards + alerting):")
    print("    kubectl patch deployment grafana -n monitoring \\")
    print("      --patch-file observability/grafana/k8s/grafana-volume-patch.yaml")
    print()
    print("  Step 9 -- Restart Grafana to apply provisioning:")
    print("    kubectl rollout restart deployment/grafana -n monitoring")
    print("    kubectl rollout status deployment/grafana -n monitoring --timeout=120s")
    print()
    print("  Step 10 -- Run verification:")
    print("    bash ~/OrderFlow/scripts/verify_phase7.sh")


if __name__ == "__main__":
    main()
