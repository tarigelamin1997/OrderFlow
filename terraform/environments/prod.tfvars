# Production environment variables — REFERENCE ONLY, not executable on Kind.
# Variables below (clickhouse_replicas, kafka_replicas, etc.) are NOT declared
# in Phase 1 Terraform module variable blocks. Running terraform plan with this
# file will fail on undeclared variables. This is intentional — these values
# document the target production configuration for cloud scaling.
# See Cross-Audit D-8 for rationale.

environment          = "prod"
cluster_name         = "orderflow-prod"
clickhouse_db_prefix = "dbt_prod"
kafka_retention_ms   = 2592000000      # 30 days
minio_storage_size   = "500Gi"

# --- Reference-only variables (require Phase 1 module amendment) ---
# clickhouse_replicas   = 3
# kafka_replicas        = 3
# spark_executor_count  = 4
# spark_executor_memory = "8Gi"
# airflow_executor      = "KubernetesExecutor"
# retention_days        = 365
