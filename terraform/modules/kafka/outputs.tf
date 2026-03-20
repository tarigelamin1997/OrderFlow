output "bootstrap_servers_internal" {
  description = "Kafka bootstrap servers (internal cluster DNS)"
  value       = "orderflow-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
}

output "bootstrap_servers_external" {
  description = "Kafka bootstrap servers (external via SSH tunnel)"
  value       = "localhost:30092"
}

output "schema_registry_url_internal" {
  description = "Schema Registry URL (internal cluster DNS)"
  value       = "http://schema-registry.kafka.svc.cluster.local:8081"
}

output "schema_registry_url_external" {
  description = "Schema Registry URL (external via SSH tunnel)"
  value       = "http://localhost:30081"
}
