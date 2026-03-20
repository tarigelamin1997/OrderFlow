output "postgres_service" {
  description = "PostgreSQL service name"
  value       = "postgres.databases.svc.cluster.local"
}

output "postgres_nodeport" {
  description = "PostgreSQL external NodePort"
  value       = 30432
}

output "mongodb_service" {
  description = "MongoDB service name"
  value       = "mongodb.databases.svc.cluster.local"
}

output "mongodb_nodeport" {
  description = "MongoDB external NodePort"
  value       = 30017
}
