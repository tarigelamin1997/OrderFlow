# OrderFlow Operations Runbook

> Phase 8 Documentation. All operations assume SSH access to the EC2 instance.
> All services are accessible via SSH tunnel only — no public NodePorts.

---

## 1. Cluster Startup Sequence

```bash
# 1a. Start the EC2 instance
aws ec2 start-instances \
  --instance-ids i-00d87b60757f192a9 \
  --profile orderflow \
  --region eu-north-1

# 1b. Wait for running state
aws ec2 wait instance-running \
  --instance-ids i-00d87b60757f192a9 \
  --profile orderflow \
  --region eu-north-1

# 1c. SSH into the instance
ssh ubuntu@13.61.247.202

# 1d. Start Docker
sudo systemctl start docker

# 1e. Wait ~2 minutes for Kind nodes to recover, then verify
kubectl get nodes
# Expected: 3 nodes Ready
#   orderflow-control-plane   Ready   control-plane
#   orderflow-worker          Ready   <none>
#   orderflow-worker2         Ready   <none>
```

### Post-Startup Required Steps

These steps are required after every cluster restart because pods use ephemeral storage.

```bash
# 1f. Remove ClickHouse default-user.xml restriction
#     (auto-generated file restricts connections to localhost)
CH_POD=$(kubectl get pod -n clickhouse -l app.kubernetes.io/name=clickhouse -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n clickhouse "$CH_POD" -- \
  rm -f /etc/clickhouse-server/users.d/default-user.xml
kubectl exec -n clickhouse "$CH_POD" -- \
  clickhouse-client --query 'SYSTEM RELOAD CONFIG'

# 1g. Re-copy Airflow DAGs (ephemeral storage — lost on pod restart)
cd ~/OrderFlow/airflow/dags && \
  tar cf - *.py | kubectl exec -n airflow airflow-0 \
    -c airflow-webserver -i -- tar xf - -C /opt/airflow/dags/

# 1h. Re-copy telemetry listener plugin
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  mkdir -p /opt/airflow/plugins
cd ~/OrderFlow/airflow/dags && \
  tar cf - dag_telemetry_listener.py | kubectl exec -n airflow airflow-0 \
    -c airflow-webserver -i -- tar xf - -C /opt/airflow/plugins/
```

Wait ~60 seconds for the Airflow scheduler to pick up the DAGs. Do **not** run
`airflow dags reserialize` — it is memory-intensive and may OOMKill the pod.

---

## 2. Cluster Shutdown Sequence

```bash
aws ec2 stop-instances \
  --instance-ids i-00d87b60757f192a9 \
  --profile orderflow \
  --region eu-north-1
```

**After shutdown, be aware:**
- MongoDB replica set may need repair on next startup (see Section 10).
- Airflow DAGs and plugins will need re-copying (see Section 1).
- ClickHouse default-user.xml restriction will reappear (see Section 1).

---

## 3. Verify System Health

### Quick Health Check

```bash
# All pods should be Running or Completed
kubectl get pods -A

# Run phase-level verification (Phases 1-7)
make verify-phase1
make verify-phase2
make verify-phase3
make verify-phase4
make verify-phase5
make verify-phase6
make verify-phase7
```

### Known Expected Failures

- **Phase 1 check 4** (Schema Registry subjects): Will fail after Phase 2
  deployment because Debezium registers additional subjects. This is expected.

### Namespace Layout

| Namespace      | Key Pods                                    |
|----------------|---------------------------------------------|
| `postgres`     | PostgreSQL (source database)                |
| `mongodb`      | MongoDB (source database)                   |
| `kafka`        | Kafka broker, Schema Registry, Kafka Connect|
| `clickhouse`   | ClickHouse server                           |
| `airflow`      | Airflow webserver + scheduler               |
| `monitoring`   | Grafana, Prometheus                         |
| `marquez`      | Marquez API + UI (OpenLineage)              |
| `default`      | SparkApplications                           |

---

## 4. How to Restart a Failed DAG

```bash
# Trigger a DAG manually
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  airflow dags trigger <dag_id>

# Check DAG run status
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  airflow dags list-runs -d <dag_id>

# View task logs for a specific run
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  airflow tasks logs <dag_id> <task_id> <execution_date>
```

### Available DAGs

| DAG ID                                | Schedule    | Purpose                     |
|---------------------------------------|-------------|-----------------------------|
| `orderflow_spark_batch_silver`        | `@daily`    | Spark batch to Delta Silver |
| `orderflow_spark_batch_gold`          | `@daily`    | Spark batch to Gold tables  |
| `orderflow_dbt_clickhouse`            | `@daily`    | dbt run (dev target)        |
| `orderflow_dbt_clickhouse_staging`    | Manual      | dbt run (staging target)    |
| `orderflow_pii_audit`                 | `@daily`    | PII audit checks            |
| `orderflow_schema_drift_monitor`      | `@daily`    | Schema drift detection      |

---

## 5. How to Re-run a Spark Job

SparkApplications run in the **default** namespace (not `spark`).

```bash
# Delete the previous SparkApplication (required before re-applying)
kubectl delete sparkapplication/<name> -n default --ignore-not-found

# Apply the job manifest
kubectl apply -f spark/manifests/<job>.yaml -n default

# Wait for completion (10 min timeout)
kubectl wait --for=condition=Completed \
  sparkapplication/<name> -n default --timeout=600s

# Check status if it does not complete
kubectl describe sparkapplication/<name> -n default

# View driver logs
kubectl logs <name>-driver -n default
```

### Spark Job Manifests

| Manifest                         | SparkApplication Name          |
|----------------------------------|--------------------------------|
| `spark_silver_orders.yaml`       | `silver-orders`                |
| `spark_silver_customers.yaml`    | `silver-customers`             |
| `spark_silver_restaurants.yaml`  | `silver-restaurants`           |
| `spark_silver_menu_items.yaml`   | `silver-menu-items`            |
| `spark_silver_order_items.yaml`  | `silver-order-items`           |
| `spark_silver_deliveries.yaml`   | `silver-deliveries`            |
| `spark_gold_batch.yaml`          | `gold-batch`                   |

---

## 6. How to Promote dbt to Staging

```bash
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  airflow dags trigger orderflow_dbt_clickhouse_staging
```

### Known Limitation (Phase 6 Deviation 9)

Due to hardcoded `schema='dbt_dev__gold'` in mart model configs, the staging
target (`dbt run --target staging`) only creates **views** in
`dbt_staging__gold`. The underlying mart **tables** remain in `dbt_dev__gold`.

To verify staging promotion:

```sql
-- Connect to ClickHouse
SELECT database, name, engine
FROM system.tables
WHERE database = 'dbt_staging__gold'
ORDER BY name;
```

---

## 7. How to Investigate a PII Audit Failure

```sql
-- Check recent PII audit failures
SELECT *
FROM gold.pii_audit_log
WHERE passed = 0
ORDER BY checked_at DESC
LIMIT 10;
```

### Investigation Steps

1. Identify which entity failed from the `entity` column.
2. Check the `check_type` column (e.g., `email_hash_format`, `phone_hash_format`).
3. Verify the Bronze source data:
   ```sql
   -- Example: check customer emails in bronze
   SELECT customer_id, email
   FROM bronze.customers
   WHERE customer_id = '<id_from_audit_log>'
   LIMIT 5;
   ```
4. For SHA-256 hash format failures, verify the hash is 64 hex characters:
   ```sql
   SELECT length(email_hash), match(email_hash, '^[a-f0-9]{64}$')
   FROM silver.customers
   WHERE customer_id = '<id>'
   LIMIT 5;
   ```
5. If the source data is valid but the hash is malformed, the Silver
   transformation pipeline has a bug — check the relevant Spark job or
   ClickHouse materialized view.

---

## 8. How to Handle Schema Drift

```sql
-- Check recent schema drift detections
SELECT *
FROM gold.schema_drift_log
ORDER BY detected_at DESC
LIMIT 10;
```

### Investigation Steps

1. Identify the affected entity and field from the drift log.
2. Compare against baseline snapshots:
   ```bash
   ls ~/OrderFlow/airflow/schema_snapshots/
   # Baseline JSON files for each entity
   ```
3. Determine if the drift is expected (planned migration) or unexpected.
4. If expected: update the baseline snapshot file and re-run the drift monitor.
5. If unexpected: investigate the source database for unplanned DDL changes.

### Updating a Baseline Snapshot

```bash
# Re-run the schema drift monitor to capture new baseline
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  airflow dags trigger orderflow_schema_drift_monitor
```

---

## 9. How to Rebuild from Scratch

This destroys the entire Kind cluster, cleans Terraform state, and rebuilds
all phases (1-7).

```bash
cd ~/OrderFlow
bash scripts/fresh_cluster_build.sh
```

**Warning:** This is a destructive operation. All data in Kafka, ClickHouse,
MinIO, PostgreSQL, and MongoDB will be lost.

After rebuild, run the full verification suite:

```bash
make verify-phase1
make verify-phase2
make verify-phase3
make verify-phase4
make verify-phase5
make verify-phase6
make verify-phase7
```

---

## 10. Common Failure Modes and Resolutions

### MongoDB CrashLoopBackOff After Restart

**Symptom:** MongoDB pod enters CrashLoopBackOff after cluster restart.
**Cause:** Replica set configuration becomes stale when the pod IP changes.

```bash
# Scale MongoDB to 0
kubectl scale statefulset mongodb -n mongodb --replicas=0

# Create a temporary repair pod
kubectl run mongo-repair -n mongodb --image=mongo:6.0 --restart=Never -- \
  mongod --replSet rs0 --bind_ip_all

# Wait for it to be ready
kubectl wait --for=condition=Ready pod/mongo-repair -n mongodb --timeout=120s

# Force-reconfig the replica set
kubectl exec -n mongodb mongo-repair -- mongosh --eval '
  rs.reconfig(
    { _id: "rs0", members: [{ _id: 0, host: "localhost:27017" }] },
    { force: true }
  )
'

# Clean up repair pod
kubectl delete pod mongo-repair -n mongodb

# Scale MongoDB back to 1
kubectl scale statefulset mongodb -n mongodb --replicas=1

# Verify
kubectl get pods -n mongodb
```

### ClickHouse Authentication Failure from EC2 Host

**Symptom:** `Authentication failed` when connecting to ClickHouse from EC2.
**Cause:** Auto-generated `default-user.xml` restricts connections to localhost.

```bash
CH_POD=$(kubectl get pod -n clickhouse -l app.kubernetes.io/name=clickhouse \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n clickhouse "$CH_POD" -- \
  rm -f /etc/clickhouse-server/users.d/default-user.xml
kubectl exec -n clickhouse "$CH_POD" -- \
  clickhouse-client --query 'SYSTEM RELOAD CONFIG'
```

### Airflow DAGs Not Visible After Pod Restart

**Symptom:** Airflow UI shows no DAGs or stale DAGs.
**Cause:** DAGs are stored in ephemeral pod storage; lost on restart.

```bash
cd ~/OrderFlow/airflow/dags && \
  tar cf - *.py | kubectl exec -n airflow airflow-0 \
    -c airflow-webserver -i -- tar xf - -C /opt/airflow/dags/
```

Wait ~60 seconds for the scheduler to detect the new files.

### Airflow OOMKilled

**Symptom:** Airflow pod restarts with reason `OOMKilled`.
**Cause:** Memory limit is 2Gi. Memory-intensive operations exceed this.

**Prevention:**
- Do **not** run `airflow dags reserialize` manually.
- Let the scheduler pick up DAG changes naturally (~60 seconds).
- Avoid triggering many DAGs simultaneously.

**Recovery:**
```bash
# Pod will auto-restart. After restart, re-copy DAGs and plugins:
cd ~/OrderFlow/airflow/dags && \
  tar cf - *.py | kubectl exec -n airflow airflow-0 \
    -c airflow-webserver -i -- tar xf - -C /opt/airflow/dags/

kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  mkdir -p /opt/airflow/plugins
tar cf - dag_telemetry_listener.py | kubectl exec -n airflow airflow-0 \
    -c airflow-webserver -i -- tar xf - -C /opt/airflow/plugins/
```

### Grafana Dashboards Missing

**Symptom:** Grafana UI shows no dashboards after pod restart.

```bash
# Reapply the volume patch and restart
kubectl apply -f monitoring/grafana-volume-patch.yaml
kubectl rollout restart deployment/grafana -n monitoring
kubectl rollout status deployment/grafana -n monitoring --timeout=120s
```

### Telemetry Listener Lost

**Symptom:** DAG telemetry events not appearing in `gold.dag_run_log`.
**Cause:** Plugin file lost after Airflow pod restart.

```bash
kubectl exec -n airflow airflow-0 -c airflow-webserver -- \
  mkdir -p /opt/airflow/plugins
cd ~/OrderFlow/airflow/dags && \
  tar cf - dag_telemetry_listener.py | kubectl exec -n airflow airflow-0 \
    -c airflow-webserver -i -- tar xf - -C /opt/airflow/plugins/
```

---

## Reference: Gold Database Ownership

The `gold` database has four phase owners. Do not write to tables owned by
another phase.

| Owner   | Tables                                          |
|---------|-------------------------------------------------|
| Phase 3 | Streaming tables (materialized views)           |
| Phase 4 | `*_batch` tables (Spark Gold batch)             |
| Phase 6 | `pii_audit_log`                                 |
| Phase 7 | `dag_run_log`, `schema_drift_log`               |

## Reference: Port Allocation

All ports are accessed via SSH tunnel. No public exposure.

| Service              | NodePort |
|----------------------|----------|
| PostgreSQL           | 30432    |
| MongoDB              | 30017    |
| Kafka                | 30092    |
| Schema Registry      | 30081    |
| Kafka Connect        | 30083    |
| ClickHouse HTTP      | 30123    |
| ClickHouse Native    | 30900    |
| MinIO S3 API         | 30910    |
| MinIO Console        | 30901    |
| Airflow UI           | 30080    |
| Grafana              | 30300    |
| Marquez API          | 30500    |
| Marquez UI           | 30301    |
| Spark UI             | 30404    |

## Reference: Key Credentials

| Service    | Username  | Password      | Notes                          |
|------------|-----------|---------------|--------------------------------|
| Grafana    | admin     | `orderflow`   | Not the default `admin` pw     |

All other credentials are managed via Kubernetes Secrets. Do not hardcode them.

## Reference: Order Status Values

Valid order status values in the pipeline:
`pending`, `accepted`, `picked_up`, `delivered`, `cancelled`

## Reference: Kind Cluster

- Kubernetes version: **1.31** (pinned — Strimzi is incompatible with 1.35)
- Topology: 1 control-plane + 2 worker nodes
- Runtime: EC2 t3.2xlarge (8 vCPU, 32 GB RAM, 100 GB EBS gp3)
- Region: eu-north-1

## SSH Tunnel Examples

```bash
# Airflow UI
ssh -L 8080:localhost:30080 ubuntu@13.61.247.202

# Grafana
ssh -L 3000:localhost:30300 ubuntu@13.61.247.202

# ClickHouse HTTP
ssh -L 8123:localhost:30123 ubuntu@13.61.247.202

# Multiple tunnels in one command
ssh -L 8080:localhost:30080 \
    -L 3000:localhost:30300 \
    -L 8123:localhost:30123 \
    ubuntu@13.61.247.202
```
