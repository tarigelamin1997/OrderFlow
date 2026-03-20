variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "minio_storage_size" {
  description = "MinIO PVC size — must fit Delta Lake + raw Parquet for all phases"
  type        = string
  default     = "30Gi"
}
