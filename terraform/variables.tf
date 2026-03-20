variable "environment" {
  description = "Deployment environment (dev / staging / prod)"
  type        = string
  default     = "dev"
}

variable "cluster_name" {
  description = "Kind cluster name — also used as kubectl context prefix (kind-<name>)"
  type        = string
  default     = "orderflow"
}

variable "clickhouse_db_prefix" {
  description = "Prefix for dbt target databases (dbt_<prefix>__gold)"
  type        = string
  default     = "dbt_dev"
}

variable "kafka_retention_ms" {
  description = "Default Kafka topic retention in milliseconds"
  type        = number
  default     = 86400000
}

variable "minio_storage_size" {
  description = "MinIO PVC size"
  type        = string
  default     = "30Gi"
}
