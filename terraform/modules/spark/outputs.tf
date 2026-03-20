output "minio_s3_url_internal" {
  description = "MinIO S3 API URL (internal cluster DNS)"
  value       = "http://minio.spark.svc.cluster.local:9000"
}

output "minio_s3_url_external" {
  description = "MinIO S3 API URL (external via SSH tunnel)"
  value       = "http://localhost:30910"
}

output "minio_console_url_external" {
  description = "MinIO Console URL (external via SSH tunnel)"
  value       = "http://localhost:30901"
}
