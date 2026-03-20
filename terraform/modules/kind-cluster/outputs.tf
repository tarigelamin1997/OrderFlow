output "cluster_name" {
  description = "Kind cluster name"
  value       = var.cluster_name
}

output "kubeconfig_context" {
  description = "kubectl context for this cluster"
  value       = "kind-${var.cluster_name}"
}
