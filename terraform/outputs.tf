output "cluster_name" {
  description = "Kind cluster name"
  value       = var.cluster_name
}

output "postgres_nodeport" {
  description = "PostgreSQL NodePort"
  value       = 30432
}

output "mongodb_nodeport" {
  description = "MongoDB NodePort"
  value       = 30017
}

output "kafka_nodeport" {
  description = "Kafka external listener NodePort"
  value       = 30092
}

output "schema_registry_nodeport" {
  description = "Schema Registry NodePort"
  value       = 30081
}

output "clickhouse_http_nodeport" {
  description = "ClickHouse HTTP NodePort"
  value       = 30123
}

output "minio_s3_nodeport" {
  description = "MinIO S3 API NodePort"
  value       = 30910
}

output "airflow_nodeport" {
  description = "Airflow UI NodePort"
  value       = 30080
}

output "grafana_nodeport" {
  description = "Grafana NodePort"
  value       = 30300
}

output "marquez_api_nodeport" {
  description = "Marquez API NodePort"
  value       = 30500
}
