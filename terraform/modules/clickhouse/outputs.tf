output "clickhouse_http_url_internal" {
  description = "ClickHouse HTTP URL (internal cluster DNS)"
  value       = "http://clickhouse.clickhouse.svc.cluster.local:8123"
}

output "clickhouse_http_url_external" {
  description = "ClickHouse HTTP URL (external via SSH tunnel)"
  value       = "http://localhost:30123"
}

output "clickhouse_native_url_internal" {
  description = "ClickHouse native protocol URL (internal)"
  value       = "clickhouse.clickhouse.svc.cluster.local:9000"
}
