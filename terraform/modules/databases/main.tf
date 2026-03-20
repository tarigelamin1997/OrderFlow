# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "databases" {
  metadata { name = "databases" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PostgreSQL 15                                                              ║
# ║  wal_level=logical, max_replication_slots=10, max_wal_senders=10           ║
# ║  Required for Debezium CDC (Phase 2).                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "kubernetes_persistent_volume_claim" "postgres" {
  metadata {
    name      = "postgres-pvc"
    namespace = kubernetes_namespace.databases.metadata[0].name
  }
  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = "standard"
    resources {
      requests = { storage = "5Gi" }
    }
  }
  wait_until_bound = false
}

resource "kubernetes_deployment" "postgres" {
  metadata {
    name      = "postgres"
    namespace = kubernetes_namespace.databases.metadata[0].name
    labels    = { app = "postgres", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "postgres" } }

    template {
      metadata { labels = { app = "postgres" } }

      spec {
        container {
          name  = "postgres"
          image = "postgres:15"

          # Pass replication settings as command args — avoids needing a custom
          # config file mount while keeping the image unmodified.
          command = [
            "postgres",
            "-c", "wal_level=logical",
            "-c", "max_replication_slots=10",
            "-c", "max_wal_senders=10",
          ]

          env {
            name  = "POSTGRES_DB"
            value = "orderflow"
          }
          env {
            name  = "POSTGRES_USER"
            value = "orderflow"
          }
          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = "orderflow-postgres-secret"
                key  = "password"
              }
            }
          }

          port {
            container_port = 5432
          }

          resources {
            requests = { cpu = "250m", memory = "256Mi" }
            limits   = { cpu = "500m", memory = "512Mi" }
          }

          volume_mount {
            name       = "postgres-data"
            mount_path = "/var/lib/postgresql/data"
          }

          readiness_probe {
            exec { command = ["pg_isready", "-U", "orderflow"] }
            initial_delay_seconds = 10
            period_seconds        = 5
          }
        }

        volume {
          name = "postgres-data"
          persistent_volume_claim { claim_name = kubernetes_persistent_volume_claim.postgres.metadata[0].name }
        }
      }
    }
  }
}

resource "kubernetes_service" "postgres" {
  metadata {
    name      = "postgres"
    namespace = kubernetes_namespace.databases.metadata[0].name
  }
  spec {
    selector = { app = "postgres" }
    port {
      port        = 5432
      target_port = 5432
      node_port   = 30432
    }
    type = "NodePort"
  }
}

# Secret created via kubectl — placeholder in manifest, actual value injected at deploy.
resource "null_resource" "postgres_secret" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
      set -euo pipefail
      kubectl create secret generic orderflow-postgres-secret \
        --namespace databases \
        --from-literal=password=orderflow_pg_pass \
        --dry-run=client -o yaml | kubectl apply -f -
    EOF
  }
  depends_on = [kubernetes_namespace.databases]
}

# Create PostgreSQL schema after the pod is ready.
# Tables must exist before seed scripts and Debezium connector run.
resource "null_resource" "postgres_schema" {
  depends_on = [kubernetes_deployment.postgres, null_resource.postgres_secret]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
      set -euo pipefail
      echo "Waiting for PostgreSQL to be ready..."
      kubectl wait --namespace databases \
        --for=condition=ready pod \
        --selector=app=postgres \
        --timeout=120s

      kubectl exec -n databases deployment/postgres -- psql -U orderflow -d orderflow -c "
        CREATE TABLE IF NOT EXISTS users (
          id          SERIAL PRIMARY KEY,
          name        VARCHAR(255) NOT NULL,
          email       VARCHAR(255),
          phone       VARCHAR(50),
          city        VARCHAR(100),
          created_at  TIMESTAMPTZ DEFAULT NOW(),
          updated_at  TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS restaurants (
          id              SERIAL PRIMARY KEY,
          name            VARCHAR(255) NOT NULL,
          cuisine         VARCHAR(100),
          city            VARCHAR(100),
          rating          DECIMAL(3,2),
          commission_rate DECIMAL(5,4),
          created_at      TIMESTAMPTZ DEFAULT NOW(),
          updated_at      TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS drivers (
          id           SERIAL PRIMARY KEY,
          name         VARCHAR(255) NOT NULL,
          phone        VARCHAR(50),
          city         VARCHAR(100),
          rating       DECIMAL(3,2),
          vehicle_type VARCHAR(50),
          created_at   TIMESTAMPTZ DEFAULT NOW(),
          updated_at   TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS orders (
          id            SERIAL PRIMARY KEY,
          user_id       INTEGER REFERENCES users(id),
          restaurant_id INTEGER REFERENCES restaurants(id),
          driver_id     INTEGER REFERENCES drivers(id),
          status        VARCHAR(50) NOT NULL DEFAULT 'pending',
          total_amount  DECIMAL(10,2),
          created_at    TIMESTAMPTZ DEFAULT NOW(),
          updated_at    TIMESTAMPTZ DEFAULT NOW()
        );
      "
      echo "PostgreSQL schema created"
    EOF
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MongoDB 6.0 — replica set rs0                                             ║
# ║  Replica set is mandatory for Debezium change streams (Phase 2).           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "kubernetes_persistent_volume_claim" "mongodb" {
  metadata {
    name      = "mongodb-pvc"
    namespace = kubernetes_namespace.databases.metadata[0].name
  }
  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = "standard"
    resources {
      requests = { storage = "5Gi" }
    }
  }
  wait_until_bound = false
}

resource "null_resource" "mongodb_secret" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
      set -euo pipefail
      kubectl create secret generic orderflow-mongo-secret \
        --namespace databases \
        --from-literal=password=orderflow_mongo_pass \
        --dry-run=client -o yaml | kubectl apply -f -
    EOF
  }
  depends_on = [kubernetes_namespace.databases]
}

resource "kubernetes_deployment" "mongodb" {
  metadata {
    name      = "mongodb"
    namespace = kubernetes_namespace.databases.metadata[0].name
    labels    = { app = "mongodb", env = var.environment }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "mongodb" } }

    template {
      metadata { labels = { app = "mongodb" } }

      spec {
        container {
          name  = "mongodb"
          image = "mongo:6.0"

          # Start mongod, wait for it to be ready, then init the replica set.
          # Init containers cannot do this: they run BEFORE the main container starts,
          # so any connection attempt to localhost:27017 from an init container would
          # loop forever. Wrapper command is the correct Kubernetes pattern here.
          # rs.initiate() is idempotent — safe on restarts.
          command = ["bash", "-c"]
          args = [<<-SCRIPT
            set -euo pipefail
            mongod --replSet rs0 --bind_ip_all &
            MONGOD_PID=$!
            until mongosh --eval "db.adminCommand('ping')" &>/dev/null; do
              echo "Waiting for mongod to be ready..."
              sleep 2
            done
            mongosh --eval "
              try {
                rs.status();
                print('Replica set rs0 already initialised');
              } catch(e) {
                rs.initiate({_id: 'rs0', members: [{_id: 0, host: 'localhost:27017'}]});
                print('Replica set rs0 initialised');
              }
            "
            wait $MONGOD_PID
          SCRIPT
          ]

          env {
            name  = "MONGO_INITDB_DATABASE"
            value = "foodtech"
          }
          env {
            name  = "MONGO_INITDB_ROOT_USERNAME"
            value = "orderflow"
          }
          env {
            name = "MONGO_INITDB_ROOT_PASSWORD"
            value_from {
              secret_key_ref {
                name = "orderflow-mongo-secret"
                key  = "password"
              }
            }
          }

          port {
            container_port = 27017
          }

          resources {
            requests = { cpu = "250m", memory = "256Mi" }
            limits   = { cpu = "500m", memory = "512Mi" }
          }

          volume_mount {
            name       = "mongodb-data"
            mount_path = "/data/db"
          }

          readiness_probe {
            exec {
              command = ["mongosh", "--eval", "db.adminCommand('ping')"]
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }
        }

        volume {
          name = "mongodb-data"
          persistent_volume_claim { claim_name = kubernetes_persistent_volume_claim.mongodb.metadata[0].name }
        }
      }
    }
  }

  depends_on = [null_resource.mongodb_secret]
}

resource "kubernetes_service" "mongodb" {
  metadata {
    name      = "mongodb"
    namespace = kubernetes_namespace.databases.metadata[0].name
  }
  spec {
    selector = { app = "mongodb" }
    port {
      port        = 27017
      target_port = 27017
      node_port   = 30017
    }
    type = "NodePort"
  }
}
