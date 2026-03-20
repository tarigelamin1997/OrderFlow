# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "monitoring" {
  metadata { name = "monitoring" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Grafana                                                                   ║
# ║  Datasources provisioned via ConfigMap — never configured manually in UI. ║
# ║  ClickHouse Altinity plugin points to clickhouse:8123.                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "kubernetes_config_map" "grafana_datasources" {
  metadata {
    name      = "grafana-datasources"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }

  data = {
    "datasources.yaml" = <<-YAML
      apiVersion: 1
      datasources:
        - name: ClickHouse
          type: vertamedia-clickhouse-datasource
          url: http://clickhouse.clickhouse.svc.cluster.local:8123
          access: proxy
          isDefault: true
          jsonData:
            defaultDatabase: gold
            # Credentials are NOT hardcoded — default ClickHouse user has no password
            useYandexCloudAuthorization: false
        - name: Prometheus
          type: prometheus
          url: http://prometheus.monitoring.svc.cluster.local:9090
          access: proxy
    YAML
  }
}

resource "kubernetes_deployment" "grafana" {
  metadata {
    name      = "grafana"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
    labels    = { app = "grafana", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "grafana" } }

    template {
      metadata { labels = { app = "grafana" } }

      spec {
        container {
          name  = "grafana"
          image = "grafana/grafana:latest"

          env {
            name  = "GF_INSTALL_PLUGINS"
            value = "vertamedia-clickhouse-datasource"
          }
          env {
            name  = "GF_SECURITY_ADMIN_PASSWORD"
            value = "orderflow"
          }
          env {
            name  = "GF_USERS_ALLOW_SIGN_UP"
            value = "false"
          }

          port { container_port = 3000 }

          resources {
            requests = { cpu = "200m", memory = "256Mi" }
            limits   = { cpu = "400m", memory = "512Mi" }
          }

          volume_mount {
            name       = "grafana-datasources"
            mount_path = "/etc/grafana/provisioning/datasources"
          }

          readiness_probe {
            http_get {
              path = "/api/health"
              port = 3000
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }
        }

        volume {
          name = "grafana-datasources"
          config_map { name = kubernetes_config_map.grafana_datasources.metadata[0].name }
        }
      }
    }
  }
}

resource "kubernetes_service" "grafana" {
  metadata {
    name      = "grafana"
    namespace = kubernetes_namespace.monitoring.metadata[0].name
  }
  spec {
    selector = { app = "grafana" }
    port {
      port        = 3000
      target_port = 3000
      node_port   = 30300
    }
    type = "NodePort"
  }
}
