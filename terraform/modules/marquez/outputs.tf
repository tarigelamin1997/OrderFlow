output "marquez_api_url_internal" {
  description = "Marquez API URL (internal cluster DNS)"
  value       = "http://marquez-api.marquez.svc.cluster.local:5000"
}

output "marquez_api_url_external" {
  description = "Marquez API URL (external via SSH tunnel)"
  value       = "http://localhost:30500"
}

output "marquez_web_url_external" {
  description = "Marquez UI URL (external via SSH tunnel)"
  value       = "http://localhost:30301"
}
