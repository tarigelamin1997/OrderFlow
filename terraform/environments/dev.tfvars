environment          = "dev"
cluster_name         = "orderflow"
clickhouse_db_prefix = "dbt_dev"
kafka_retention_ms   = 86400000
minio_storage_size   = "10Gi"

# Phase 8 reference variables — these are the dev defaults used on Kind.
# Variables below are accepted by the existing Phase 1 Terraform modules.
# See staging.tfvars and prod.tfvars for production scaling reference.
