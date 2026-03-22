# Staging environment variables — REFERENCE ONLY, not executable on Kind.
# Variables below (clickhouse_replicas, kafka_replicas, etc.) are NOT declared
# in Phase 1 Terraform module variable blocks. Running terraform plan with this
# file will fail on undeclared variables. This is intentional — these values
# document the target staging configuration for production scaling.
# See Cross-Audit D-8 for rationale.

environment          = "staging"
cluster_name         = "orderflow-staging"
clickhouse_db_prefix = "dbt_staging"
kafka_retention_ms   = 604800000       # 7 days
minio_storage_size   = "50Gi"

# --- Reference-only variables (require Phase 1 module amendment) ---
# clickhouse_replicas   = 1
# kafka_replicas        = 3
# spark_executor_count  = 2
# spark_executor_memory = "4Gi"
# airflow_executor      = "LocalExecutor"
# retention_days        = 30
