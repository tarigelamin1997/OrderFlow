# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "marquez" {
  metadata { name = "marquez" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Marquez 0.48.0 — data lineage tracking                                   ║
# ║  Deployed in Phase 1 so CDC lineage from Phase 2+ is captured from day 1. ║
# ║  In-memory H2 backend — lineage is re-emitted on each pipeline run.       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "kubernetes_deployment" "marquez_api" {
  metadata {
    name      = "marquez-api"
    namespace = kubernetes_namespace.marquez.metadata[0].name
    labels    = { app = "marquez-api", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "marquez-api" } }

    template {
      metadata { labels = { app = "marquez-api" } }

      spec {
        container {
          name  = "marquez-api"
          image = "marquezproject/marquez:0.48.0"

          env {
            name  = "MARQUEZ_PORT"
            value = "5000"
          }
          env {
            name  = "MARQUEZ_ADMIN_PORT"
            value = "5001"
          }

          port {
            container_port = 5000
            name           = "api"
          }
          port {
            container_port = 5001
            name           = "admin"
          }

          resources {
            requests = { cpu = "200m", memory = "256Mi" }
            limits   = { cpu = "400m", memory = "512Mi" }
          }

          readiness_probe {
            http_get {
              path = "/api/v1/namespaces"
              port = 5000
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "marquez_api" {
  metadata {
    name      = "marquez-api"
    namespace = kubernetes_namespace.marquez.metadata[0].name
  }
  spec {
    selector = { app = "marquez-api" }
    port {
      port        = 5000
      target_port = 5000
      node_port   = 30500
    }
    type = "NodePort"
  }
}

resource "kubernetes_deployment" "marquez_web" {
  metadata {
    name      = "marquez-web"
    namespace = kubernetes_namespace.marquez.metadata[0].name
    labels    = { app = "marquez-web", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "marquez-web" } }

    template {
      metadata { labels = { app = "marquez-web" } }

      spec {
        container {
          name  = "marquez-web"
          image = "marquezproject/marquez-web:0.48.0"

          env {
            name  = "MARQUEZ_HOST"
            value = "marquez-api.marquez.svc.cluster.local"
          }
          env {
            name  = "MARQUEZ_PORT"
            value = "5000"
          }

          port {
            container_port = 3000
          }

          resources {
            requests = { cpu = "100m", memory = "128Mi" }
            limits   = { cpu = "200m", memory = "256Mi" }
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 3000
            }
            initial_delay_seconds = 15
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "marquez_web" {
  metadata {
    name      = "marquez-web"
    namespace = kubernetes_namespace.marquez.metadata[0].name
  }
  spec {
    selector = { app = "marquez-web" }
    port {
      port        = 3000
      target_port = 3000
      node_port   = 30301
    }
    type = "NodePort"
  }
}
