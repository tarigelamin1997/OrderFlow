# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "spark" {
  metadata { name = "spark" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Spark Operator                                                            ║
# ║  Manages SparkApplication lifecycle via CRDs.                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "helm_release" "spark_operator" {
  name             = "spark-operator"
  repository       = "https://kubeflow.github.io/spark-operator"
  chart            = "spark-operator"
  namespace        = kubernetes_namespace.spark.metadata[0].name
  create_namespace = false
  wait             = true
  timeout          = 180

  set {
    name  = "webhook.enable"
    value = "true"
  }
  set {
    name  = "sparkJobNamespace"
    value = kubernetes_namespace.spark.metadata[0].name
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MinIO — S3-compatible object store                                        ║
# ║  3 buckets: orderflow-raw, orderflow-silver, orderflow-checkpoints        ║
# ║  Spark writes Delta Lake checkpoints to orderflow-checkpoints.            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "null_resource" "minio_secret" {
  provisioner "local-exec" {
    command = <<-EOF
      set -euo pipefail
      kubectl create secret generic orderflow-minio-secret \
        --namespace spark \
        --from-literal=access-key=orderflow \
        --from-literal=secret-key=orderflow_minio_pass \
        --dry-run=client -o yaml | kubectl apply -f -
    EOF
  }
  depends_on = [kubernetes_namespace.spark]
}

resource "kubernetes_persistent_volume_claim" "minio" {
  metadata {
    name      = "minio-pvc"
    namespace = kubernetes_namespace.spark.metadata[0].name
  }
  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = "standard"
    resources {
      requests = { storage = var.minio_storage_size }
    }
  }
}

resource "kubernetes_deployment" "minio" {
  metadata {
    name      = "minio"
    namespace = kubernetes_namespace.spark.metadata[0].name
    labels    = { app = "minio", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "minio" } }

    template {
      metadata { labels = { app = "minio" } }

      spec {
        container {
          name  = "minio"
          image = "minio/minio:latest"

          args = ["server", "/data", "--console-address", ":9001"]

          env {
            name = "MINIO_ROOT_USER"
            value_from {
              secret_key_ref {
                name = "orderflow-minio-secret"
                key  = "access-key"
              }
            }
          }
          env {
            name = "MINIO_ROOT_PASSWORD"
            value_from {
              secret_key_ref {
                name = "orderflow-minio-secret"
                key  = "secret-key"
              }
            }
          }

          port { container_port = 9000 name = "s3" }
          port { container_port = 9001 name = "console" }

          resources {
            requests = { cpu = "200m", memory = "256Mi" }
            limits   = { cpu = "500m", memory = "512Mi" }
          }

          volume_mount {
            name       = "minio-data"
            mount_path = "/data"
          }

          readiness_probe {
            http_get {
              path = "/minio/health/ready"
              port = 9000
            }
            initial_delay_seconds = 15
            period_seconds        = 5
          }
        }

        volume {
          name = "minio-data"
          persistent_volume_claim { claim_name = kubernetes_persistent_volume_claim.minio.metadata[0].name }
        }
      }
    }
  }

  depends_on = [null_resource.minio_secret]
}

resource "kubernetes_service" "minio" {
  metadata {
    name      = "minio"
    namespace = kubernetes_namespace.spark.metadata[0].name
  }
  spec {
    selector = { app = "minio" }

    # S3 API port — ClickHouse native (9000) is on 30900; MinIO S3 is on 30910
    port {
      name        = "s3"
      port        = 9000
      target_port = 9000
      node_port   = 30910
    }

    port {
      name        = "console"
      port        = 9001
      target_port = 9001
      node_port   = 30901
    }

    type = "NodePort"
  }
}

# Create the 3 MinIO buckets after MinIO is ready.
# Phase 2 S3 Sink writes to orderflow-raw.
# Phase 4 Spark reads from orderflow-raw, writes to orderflow-silver.
# Phase 4 Spark writes checkpoints to orderflow-checkpoints.
resource "null_resource" "minio_buckets" {
  depends_on = [kubernetes_deployment.minio]

  provisioner "local-exec" {
    command = <<-EOF
      set -euo pipefail
      echo "Waiting for MinIO to be ready..."
      kubectl wait --namespace spark \
        --for=condition=ready pod \
        --selector=app=minio \
        --timeout=120s

      # Use mc (MinIO client) via kubectl exec to create buckets idempotently
      kubectl exec -n spark deployment/minio -- sh -c "
        mc alias set local http://localhost:9000 orderflow orderflow_minio_pass
        mc mb --ignore-existing local/orderflow-raw
        mc mb --ignore-existing local/orderflow-silver
        mc mb --ignore-existing local/orderflow-checkpoints
        echo 'Buckets created: orderflow-raw, orderflow-silver, orderflow-checkpoints'
      "
    EOF
  }
}
