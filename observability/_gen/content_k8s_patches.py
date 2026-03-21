"""Content for Kubernetes patch and ConfigMap reference files (Phase 7)."""


def grafana_dashboard_configmap_yaml() -> str:
    return """\
# observability/grafana/k8s/grafana-dashboard-configmap.yaml
# Phase 7: Reference commands for creating Grafana dashboard ConfigMaps.
# This is NOT applied with kubectl apply. Run these commands manually after
# running gen_phase7.py and copying the files to the EC2 instance.
#
# Step 1 -- Create ConfigMap from all dashboard JSON files:
#
#   kubectl create configmap grafana-dashboards-json \\
#     --from-file=pipeline_health.json=observability/grafana/dashboards/pipeline_health.json \\
#     --from-file=data_quality.json=observability/grafana/dashboards/data_quality.json \\
#     --from-file=clickhouse_ops.json=observability/grafana/dashboards/clickhouse_ops.json \\
#     --from-file=business_metrics.json=observability/grafana/dashboards/business_metrics.json \\
#     --from-file=finops_resources.json=observability/grafana/dashboards/finops_resources.json \\
#     -n monitoring
#
# Step 2 -- Create ConfigMap from provisioning YAML:
#
#   kubectl create configmap grafana-dashboards-provisioning \\
#     --from-file=orderflow.yaml=observability/grafana/provisioning/dashboards/orderflow.yaml \\
#     -n monitoring
#
# Step 3 -- Create ConfigMap from alerting YAML:
#
#   kubectl create configmap grafana-alerting-provisioning \\
#     --from-file=orderflow-alerts.yaml=observability/grafana/provisioning/alerting/orderflow-alerts.yaml \\
#     -n monitoring
#
# Step 4 -- Apply the volume patch to the Grafana deployment:
#
#   kubectl patch deployment grafana -n monitoring \\
#     --patch-file observability/grafana/k8s/grafana-volume-patch.yaml
#
# Step 5 -- Restart Grafana to pick up new config:
#
#   kubectl rollout restart deployment/grafana -n monitoring
"""


def grafana_volume_patch_yaml() -> str:
    return """\
# observability/grafana/k8s/grafana-volume-patch.yaml
# Phase 7: Strategic merge patch for the grafana Deployment in monitoring namespace.
# Mounts dashboard JSON, dashboard provisioning config, and alerting config
# into the Grafana container from ConfigMaps created in the apply sequence.
#
# Apply with:
#   kubectl patch deployment grafana -n monitoring \\
#     --patch-file observability/grafana/k8s/grafana-volume-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: monitoring
spec:
  template:
    spec:
      containers:
        - name: grafana
          volumeMounts:
            - name: dashboards-json
              mountPath: /etc/grafana/provisioning/dashboards/json
              readOnly: true
            - name: dashboards-provisioning
              mountPath: /etc/grafana/provisioning/dashboards/orderflow.yaml
              subPath: orderflow.yaml
              readOnly: true
            - name: alerting-provisioning
              mountPath: /etc/grafana/provisioning/alerting/orderflow-alerts.yaml
              subPath: orderflow-alerts.yaml
              readOnly: true
      volumes:
        - name: dashboards-json
          configMap:
            name: grafana-dashboards-json
        - name: dashboards-provisioning
          configMap:
            name: grafana-dashboards-provisioning
        - name: alerting-provisioning
          configMap:
            name: grafana-alerting-provisioning
"""


def airflow_openlineage_patch_yaml() -> str:
    return """\
# observability/openlineage/k8s/airflow-openlineage-patch.yaml
# Phase 7: Strategic merge patch for the airflow StatefulSet in airflow namespace.
# Adds OpenLineage env vars and mounts the airflow-plugins ConfigMap so that
# dag_telemetry_listener.py is available inside the pod.
#
# Apply with:
#   kubectl patch statefulset airflow -n airflow \\
#     --patch-file observability/openlineage/k8s/airflow-openlineage-patch.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: airflow
  namespace: airflow
spec:
  template:
    spec:
      containers:
        - name: airflow-webserver
          env:
            - name: AIRFLOW__OPENLINEAGE__DISABLED
              value: "false"
            - name: AIRFLOW__OPENLINEAGE__TRANSPORT
              value: >-
                {"type": "http", "url":
                "http://marquez-api.marquez.svc.cluster.local:5000",
                "endpoint": "api/v1/lineage"}
            - name: AIRFLOW__OPENLINEAGE__NAMESPACE
              value: "orderflow"
          volumeMounts:
            - name: airflow-plugins
              mountPath: /opt/airflow/plugins
              readOnly: false
      volumes:
        - name: airflow-plugins
          configMap:
            name: airflow-plugins
"""


def plugins_configmap_yaml() -> str:
    return """\
# observability/k8s/plugins-configmap.yaml
# Phase 7: Reference command for creating the airflow-plugins ConfigMap.
# This is NOT applied with kubectl apply. Run the command below after
# gen_phase7.py has written dag_telemetry_listener.py.
#
# Create ConfigMap from the telemetry listener plugin:
#
#   kubectl create configmap airflow-plugins \\
#     --from-file=dag_telemetry_listener.py=observability/plugins/dag_telemetry_listener.py \\
#     -n airflow
#
# To update an existing ConfigMap:
#
#   kubectl create configmap airflow-plugins \\
#     --from-file=dag_telemetry_listener.py=observability/plugins/dag_telemetry_listener.py \\
#     -n airflow --dry-run=client -o yaml | kubectl apply -f -
#
# After creating the ConfigMap, apply the StatefulSet patch:
#
#   kubectl patch statefulset airflow -n airflow \\
#     --patch-file observability/openlineage/k8s/airflow-openlineage-patch.yaml
#
# Then restart Airflow to load the plugin:
#
#   kubectl rollout restart statefulset/airflow -n airflow
"""


def openlineage_yml() -> str:
    return """\
# observability/openlineage/openlineage.yml
# Phase 7: OpenLineage client configuration reference.
# The actual configuration is injected via environment variables in the
# airflow-openlineage-patch.yaml (AIRFLOW__OPENLINEAGE__TRANSPORT).
# This file is for documentation / local development reference only.
transport:
  type: http
  url: http://marquez-api.marquez.svc.cluster.local:5000
  endpoint: api/v1/lineage

# Namespace groups all lineage events from this Airflow instance.
# Must match the AIRFLOW__OPENLINEAGE__NAMESPACE env var.
namespace: orderflow
"""
