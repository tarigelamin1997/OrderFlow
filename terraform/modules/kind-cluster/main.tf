locals {
  kind_config = <<-YAML
    kind: Cluster
    apiVersion: kind.x-k8s.io/v1alpha4
    name: ${var.cluster_name}
    nodes:
      - role: control-plane
        extraPortMappings:
          - { containerPort: 30432, hostPort: 30432 }
          - { containerPort: 30017, hostPort: 30017 }
          - { containerPort: 30092, hostPort: 30092 }
          - { containerPort: 30081, hostPort: 30081 }
          - { containerPort: 30083, hostPort: 30083 }
          - { containerPort: 30123, hostPort: 30123 }
          - { containerPort: 30900, hostPort: 30900 }
          - { containerPort: 30910, hostPort: 30910 }
          - { containerPort: 30901, hostPort: 30901 }
          - { containerPort: 30080, hostPort: 30080 }
          - { containerPort: 30300, hostPort: 30300 }
          - { containerPort: 30500, hostPort: 30500 }
          - { containerPort: 30301, hostPort: 30301 }
          - { containerPort: 30404, hostPort: 30404 }
      - role: worker
      - role: worker
  YAML
}

# Write Kind config to a temp file and create the cluster.
# delete_before_create = true so re-apply is idempotent.
resource "null_resource" "kind_cluster" {
  triggers = {
    cluster_name = var.cluster_name
    config_hash  = sha256(local.kind_config)
  }

  provisioner "local-exec" {
    command = <<-EOF
      set -euo pipefail
      # Write config
      cat > /tmp/kind-config-${var.cluster_name}.yaml << 'KINDEOF'
${local.kind_config}
KINDEOF

      # Create cluster if it does not already exist
      if kind get clusters | grep -q "^${var.cluster_name}$"; then
        echo "Kind cluster '${var.cluster_name}' already exists — skipping creation"
      else
        kind create cluster --name ${var.cluster_name} \
          --config /tmp/kind-config-${var.cluster_name}.yaml
        echo "Kind cluster '${var.cluster_name}' created"
      fi

      # Merge kubeconfig (Kind writes to ~/.kube/config by default)
      kind export kubeconfig --name ${var.cluster_name}
    EOF
  }

  provisioner "local-exec" {
    when    = destroy
    command = "kind delete cluster --name ${var.cluster_name} || true"
  }
}

# Wait for all nodes to reach Ready state before dependent modules proceed.
resource "null_resource" "wait_for_nodes" {
  depends_on = [null_resource.kind_cluster]

  provisioner "local-exec" {
    command = <<-EOF
      set -euo pipefail
      echo "Waiting for Kind nodes to be Ready..."
      kubectl wait node --all --for=condition=Ready \
        --context kind-${var.cluster_name} --timeout=120s
      echo "All nodes Ready"
    EOF
  }
}
