#!/bin/bash
set -euo pipefail

echo "=== OrderFlow Fresh Cluster Build ==="
echo "This destroys the existing cluster and rebuilds from scratch."
read -p "Continue? (y/N) " confirm
[[ "$confirm" == "y" ]] || exit 0

echo "Step 1: Destroy existing cluster and clean Terraform state"
cd terraform && terraform destroy -var-file=environments/dev.tfvars -auto-approve 2>/dev/null || true && cd ..
kind delete cluster --name orderflow 2>/dev/null || true
rm -f terraform/terraform.tfstate terraform/terraform.tfstate.backup
echo "  Cluster destroyed, Terraform state cleaned"

echo "Step 2: Phase 1 — Infrastructure"
make run-phase1
make verify-phase1

echo "Step 3: Phase 2 — CDC Pipeline"
make run-phase2
make verify-phase2

echo "Step 4: Phase 3 — ClickHouse Schema"
make run-phase3
make verify-phase3

echo "Step 5: Phase 4 — Spark Batch"
make run-phase4
make verify-phase4

echo "Step 6: Phase 5 — dbt Layer"
make run-phase5
make verify-phase5

echo "Step 7: Phase 6 — Airflow Orchestration"
make run-phase6
# Remove ClickHouse default-user restriction
CH_POD=$(kubectl get pod -n clickhouse -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n clickhouse $CH_POD -- rm -f /etc/clickhouse-server/users.d/default-user.xml
kubectl exec -n clickhouse $CH_POD -- clickhouse-client --query 'SYSTEM RELOAD CONFIG'
# Deploy DAGs to Airflow pod
cd airflow/dags && tar cf - *.py | kubectl exec -n airflow airflow-0 -c airflow-webserver -i -- tar xf - -C /opt/airflow/dags/ && cd ../..
sleep 60  # Wait for scheduler to parse DAGs
# Trigger DAGs manually
kubectl exec -n airflow airflow-0 -c airflow-webserver -- airflow dags trigger orderflow_batch_ingestion
sleep 300  # Wait for batch pipeline
kubectl exec -n airflow airflow-0 -c airflow-webserver -- airflow dags trigger orderflow_dbt_clickhouse_staging
sleep 120
make verify-phase6

echo "Step 8: Phase 7 — Observability"
make run-phase7
# Re-copy telemetry listener plugin (Phase 7 Deviation 1)
kubectl exec -n airflow airflow-0 -c airflow-webserver -- mkdir -p /opt/airflow/plugins
cd observability/plugins && tar cf - dag_telemetry_listener.py | kubectl exec -n airflow airflow-0 -c airflow-webserver -i -- tar xf - -C /opt/airflow/plugins/ && cd ../..
sleep 60
make verify-phase7

echo "=== Fresh Cluster Build Complete ==="
echo "Total phases: 7 | All verified"
