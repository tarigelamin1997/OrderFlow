"""Content for Grafana provisioning YAML files."""


def grafana_dashboards_provisioning_yaml() -> str:
    return """\
# observability/grafana/provisioning/dashboards/orderflow.yaml
# Phase 7: Grafana dashboard provisioning configuration.
# Tells Grafana where to find dashboard JSON files at startup.
apiVersion: 1

providers:
  - name: "orderflow-dashboards"
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards/json
      foldersFromFilesStructure: false
"""


def grafana_alerts_yaml() -> str:
    return """\
# observability/grafana/provisioning/alerting/orderflow-alerts.yaml
# Phase 7: Grafana Unified Alerting rules for OrderFlow pipeline health.
# Uses datasourceUid matching the ClickHouse datasource provisioned in Phase 3.
apiVersion: 1

groups:
  - orgId: 1
    name: "orderflow-pipeline"
    folder: "OrderFlow Alerts"
    interval: 5m
    rules:

      - uid: "of-alert-dag-failures"
        title: "High DAG Failure Rate"
        condition: "C"
        data:
          - refId: "A"
            datasourceUid: "PDEE91DDB90597936"
            model:
              rawSql: >
                SELECT count() AS failure_count
                FROM gold.dag_run_log
                WHERE state = 'failed'
                AND event_timestamp >= now() - INTERVAL 1 HOUR
              format: table
          - refId: "C"
            datasourceUid: "__expr__"
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [5]
                    type: gt
                  query:
                    params: ["A"]
        noDataState: OK
        execErrState: Alerting
        for: 5m
        annotations:
          summary: "More than 5 DAG task failures in the last hour"
        labels:
          severity: warning

      - uid: "of-alert-schema-drift"
        title: "Schema Drift Detected"
        condition: "C"
        data:
          - refId: "A"
            datasourceUid: "PDEE91DDB90597936"
            model:
              rawSql: >
                SELECT count() AS drift_count
                FROM gold.schema_drift_log
                WHERE drift_detected = 1
                AND checked_at >= now() - INTERVAL 24 HOUR
              format: table
          - refId: "C"
            datasourceUid: "__expr__"
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [0]
                    type: gt
                  query:
                    params: ["A"]
        noDataState: OK
        execErrState: Alerting
        for: 1m
        annotations:
          summary: "Schema drift detected in silver tables within the last 24 hours"
        labels:
          severity: critical

      - uid: "of-alert-pii-failures"
        title: "PII Audit Failures"
        condition: "C"
        data:
          - refId: "A"
            datasourceUid: "PDEE91DDB90597936"
            model:
              rawSql: >
                SELECT sum(failure_count) AS total_failures
                FROM gold.pii_audit_log
                WHERE audit_timestamp >= now() - INTERVAL 24 HOUR
              format: table
          - refId: "C"
            datasourceUid: "__expr__"
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [0]
                    type: gt
                  query:
                    params: ["A"]
        noDataState: OK
        execErrState: Alerting
        for: 1m
        annotations:
          summary: "PII audit failures detected in the last 24 hours"
        labels:
          severity: critical

      - uid: "of-alert-ch-slow-queries"
        title: "ClickHouse Slow Queries"
        condition: "C"
        data:
          - refId: "A"
            datasourceUid: "PDEE91DDB90597936"
            model:
              rawSql: >
                SELECT count() AS slow_count
                FROM system.query_log
                WHERE query_duration_ms > 30000
                AND event_time >= now() - INTERVAL 1 HOUR
                AND type = 'QueryFinish'
              format: table
          - refId: "C"
            datasourceUid: "__expr__"
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [10]
                    type: gt
                  query:
                    params: ["A"]
        noDataState: OK
        execErrState: Alerting
        for: 5m
        annotations:
          summary: "More than 10 queries exceeded 30s in the last hour"
        labels:
          severity: warning

      - uid: "of-alert-no-dag-runs"
        title: "No DAG Activity"
        condition: "C"
        data:
          - refId: "A"
            datasourceUid: "PDEE91DDB90597936"
            model:
              rawSql: >
                SELECT count() AS run_count
                FROM gold.dag_run_log
                WHERE event_timestamp >= now() - INTERVAL 6 HOUR
              format: table
          - refId: "C"
            datasourceUid: "__expr__"
            model:
              type: threshold
              conditions:
                - evaluator:
                    params: [1]
                    type: lt
                  query:
                    params: ["A"]
        noDataState: Alerting
        execErrState: Alerting
        for: 10m
        annotations:
          summary: "No DAG runs recorded in ClickHouse for 6 hours — pipeline may be stalled"
        labels:
          severity: warning
"""
