# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "clickhouse" {
  metadata { name = "clickhouse" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ClickHouse 24.8 LTS                                                       ║
# ║  Memory: 3GB per query, 6GB server total (32GB RAM allows this).          ║
# ║  5 databases pre-created on startup via init SQL.                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Memory limits per the plan — 3GB per query, 6GB server
resource "kubernetes_config_map" "clickhouse_config" {
  metadata {
    name      = "clickhouse-config"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
  }

  data = {
    "config.xml" = <<-XML
      <clickhouse>
        <max_memory_usage>3221225472</max_memory_usage>
        <max_server_memory_usage>6442450944</max_server_memory_usage>
        <max_concurrent_queries>100</max_concurrent_queries>
        <listen_host>0.0.0.0</listen_host>
      </clickhouse>
    XML

    # Init SQL: pre-create all 5 databases on first startup.
    # Phases 2-7 each own specific databases — see CLAUDE.md for ownership map.
    "init.sql" = <<-SQL
      CREATE DATABASE IF NOT EXISTS bronze;
      CREATE DATABASE IF NOT EXISTS silver;
      CREATE DATABASE IF NOT EXISTS gold;
      CREATE DATABASE IF NOT EXISTS dbt_dev__gold;
      CREATE DATABASE IF NOT EXISTS dbt_staging__gold;
    SQL
  }
}

resource "kubernetes_persistent_volume_claim" "clickhouse" {
  metadata {
    name      = "clickhouse-pvc"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
  }
  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = "standard"
    resources {
      requests = { storage = "20Gi" }
    }
  }
}

resource "kubernetes_deployment" "clickhouse" {
  metadata {
    name      = "clickhouse"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
    labels    = { app = "clickhouse", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "clickhouse" } }

    template {
      metadata { labels = { app = "clickhouse" } }

      spec {
        container {
          name  = "clickhouse"
          image = "clickhouse/clickhouse-server:24.8"

          port { container_port = 8123 name = "http" }
          port { container_port = 9000 name = "native" }

          resources {
            requests = { cpu = "1000m", memory = "3Gi" }
            limits   = { cpu = "3000m", memory = "6Gi" }
          }

          volume_mount {
            name       = "clickhouse-data"
            mount_path = "/var/lib/clickhouse"
          }

          # Custom config for memory limits
          volume_mount {
            name       = "clickhouse-config"
            mount_path = "/etc/clickhouse-server/config.d/custom.xml"
            sub_path   = "config.xml"
          }

          # Init SQL runs via entrypoint — creates 5 databases on first launch
          volume_mount {
            name       = "clickhouse-config"
            mount_path = "/docker-entrypoint-initdb.d/init.sql"
            sub_path   = "init.sql"
          }

          readiness_probe {
            http_get {
              path = "/ping"
              port = 8123
            }
            initial_delay_seconds = 15
            period_seconds        = 5
          }
        }

        volume {
          name = "clickhouse-data"
          persistent_volume_claim { claim_name = kubernetes_persistent_volume_claim.clickhouse.metadata[0].name }
        }

        volume {
          name = "clickhouse-config"
          config_map { name = kubernetes_config_map.clickhouse_config.metadata[0].name }
        }
      }
    }
  }
}

resource "kubernetes_service" "clickhouse" {
  metadata {
    name      = "clickhouse"
    namespace = kubernetes_namespace.clickhouse.metadata[0].name
  }
  spec {
    selector = { app = "clickhouse" }

    port {
      name        = "http"
      port        = 8123
      target_port = 8123
      node_port   = 30123
    }

    port {
      name        = "native"
      port        = 9000
      target_port = 9000
      node_port   = 30900
    }

    type = "NodePort"
  }
}
