# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "airflow" {
  metadata { name = "airflow" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Build custom Airflow image and load it into Kind                          ║
# ║  Image: apache/airflow:2.10.0 + dbt + GE + openlineage                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Build the custom image on EC2 and load it into the Kind cluster.
# imagePullPolicy: Never tells K8s to use the pre-loaded image without pulling.
resource "null_resource" "airflow_image" {
  triggers = {
    dockerfile_hash = filesha256("${path.root}/../airflow/Dockerfile")
  }

  provisioner "local-exec" {
    command = <<-EOF
      set -euo pipefail
      echo "Building custom Airflow image..."
      docker build -t orderflow/airflow:2.10.0 ${path.root}/../airflow/
      echo "Loading image into Kind cluster..."
      kind load docker-image orderflow/airflow:2.10.0 --name orderflow
      echo "Airflow image loaded into Kind"
    EOF
  }
}

# Airflow metadata DB — using the PostgreSQL deployed in databases module.
resource "null_resource" "airflow_db_init" {
  depends_on = [kubernetes_namespace.airflow, null_resource.airflow_image]

  provisioner "local-exec" {
    command = <<-EOF
      set -euo pipefail
      # Create airflow database and user in PostgreSQL
      kubectl exec -n databases deployment/postgres -- psql -U orderflow -d orderflow -c "
        CREATE DATABASE airflow;
        CREATE USER airflow WITH PASSWORD 'airflow_pass';
        GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;
      " 2>/dev/null || echo "Airflow DB already exists — skipping"
    EOF
  }
}

# ── ConfigMap: Airflow environment config ─────────────────────────────────────
resource "kubernetes_config_map" "airflow_config" {
  metadata {
    name      = "airflow-config"
    namespace = kubernetes_namespace.airflow.metadata[0].name
  }

  data = {
    AIRFLOW__CORE__EXECUTOR                          = "LocalExecutor"
    AIRFLOW__CORE__LOAD_EXAMPLES                     = "False"
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN              = "postgresql+psycopg2://airflow:airflow_pass@postgres.databases.svc.cluster.local:5432/airflow"
    AIRFLOW__CORE__FERNET_KEY                        = "46BKJoQYlPPOexq0OhDZnIlNepKFf87WFwLt0nfd7gY="
    AIRFLOW__WEBSERVER__SECRET_KEY                   = "orderflow_airflow_secret"
    AIRFLOW__LINEAGE__BACKEND                        = "openlineage"
    AIRFLOW__OPENLINEAGE__TRANSPORT                  = "{\"type\": \"http\", \"url\": \"http://marquez-api.marquez.svc.cluster.local:5000\"}"
    AIRFLOW__OPENLINEAGE__NAMESPACE                  = "orderflow"
  }
}

# ── StatefulSet: Airflow (LocalExecutor) ─────────────────────────────────────
resource "kubernetes_stateful_set" "airflow" {
  depends_on = [null_resource.airflow_db_init]

  metadata {
    name      = "airflow"
    namespace = kubernetes_namespace.airflow.metadata[0].name
    labels    = { app = "airflow", env = var.environment }
  }

  spec {
    service_name = "airflow"
    replicas     = 1
    selector { match_labels = { app = "airflow" } }

    template {
      metadata { labels = { app = "airflow" } }

      spec {
        # DB migration runs as an init container so the webserver starts clean.
        init_container {
          name    = "airflow-db-migrate"
          image   = "orderflow/airflow:2.10.0"
          command = ["airflow", "db", "migrate"]
          env_from {
            config_map_ref { name = kubernetes_config_map.airflow_config.metadata[0].name }
          }
          image_pull_policy = "Never"
        }

        container {
          name  = "airflow-webserver"
          image = "orderflow/airflow:2.10.0"

          # Start both webserver and scheduler in one container (LocalExecutor).
          # Phase 5+ can split them if needed — single-container is fine for dev.
          command = ["bash", "-c", "airflow scheduler & airflow webserver"]

          env_from {
            config_map_ref { name = kubernetes_config_map.airflow_config.metadata[0].name }
          }

          port { container_port = 8080 }

          resources {
            requests = { cpu = "500m", memory = "1Gi" }
            limits   = { cpu = "1000m", memory = "2Gi" }
          }

          image_pull_policy = "Never"

          readiness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 60
            period_seconds        = 15
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "airflow" {
  metadata {
    name      = "airflow"
    namespace = kubernetes_namespace.airflow.metadata[0].name
  }
  spec {
    selector = { app = "airflow" }
    port {
      port        = 8080
      target_port = 8080
      node_port   = 30080
    }
    type = "NodePort"
  }
}
